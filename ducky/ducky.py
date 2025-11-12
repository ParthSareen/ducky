from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List

from ollama import AsyncClient
from contextlib import nullcontext

try:  # prompt_toolkit is optional at runtime
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.patch_stdout import patch_stdout
except ImportError:  # pragma: no cover - fallback mode
    PromptSession = None  # type: ignore[assignment]
    FileHistory = None  # type: ignore[assignment]
    KeyBindings = None  # type: ignore[assignment]

    def patch_stdout() -> nullcontext:
        return nullcontext()
from rich.console import Console


@dataclass
class AssistantResult:
    content: str
    command: str | None
    thinking: str | None = None


@dataclass
class ShellResult:
    command: str
    stdout: str
    stderr: str
    returncode: int


HISTORY_DIR = Path.home() / ".ducky"
PROMPT_HISTORY_FILE = HISTORY_DIR / "prompt_history"
CONVERSATION_LOG_FILE = HISTORY_DIR / "conversation.log"
console = Console()


def ensure_history_dir() -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


class ConversationLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def log_user(self, content: str) -> None:
        if content.strip():
            self._append({"role": "user", "content": content})

    def log_assistant(self, content: str, command: str | None) -> None:
        entry: Dict[str, Any] = {"role": "assistant", "content": content}
        if command:
            entry["suggested_command"] = command
        self._append(entry)

    def log_shell(self, result: ShellResult) -> None:
        self._append(
            {
                "role": "shell",
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        )

    def _append(self, entry: Dict[str, Any]) -> None:
        entry["timestamp"] = datetime.utcnow().isoformat()
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")


def print_shell_result(result: ShellResult) -> None:
    printed = False
    if result.stdout.strip():
        console.print(result.stdout.rstrip(), highlight=False)
        printed = True
    if result.stderr.strip():
        if printed:
            console.print()
        console.print("[stderr]", style="bold red")
        console.print(result.stderr.rstrip(), style="red", highlight=False)
        printed = True
    if result.returncode != 0 or not printed:
        suffix = (
            f"(exit status {result.returncode})"
            if result.returncode != 0
            else "(command produced no output)"
        )
        console.print(suffix, style="yellow")


async def run_shell_and_print(
    assistant: RubberDuck,
    command: str,
    logger: ConversationLogger | None = None,
) -> None:
    if not command:
        console.print("No command provided.", style="yellow")
        return
    console.print(f"$ {command}", style="bold magenta")
    result = await assistant.run_shell_command(command)
    print_shell_result(result)
    if logger:
        logger.log_shell(result)


class RubberDuck:
    def __init__(
        self, model: str, quick: bool = False, command_mode: bool = False
    ) -> None:
        self.system_prompt = dedent(
            """
            You are a pair programming tool called Ducky or RubberDucky to help
            developers debug, think through design decisions, and write code.
            Help the user reason about their approach and provide feedback on
            the code. Think step by step and ask clarifying questions if
            needed.

            When the user provides git status output or similar multi-line terminal
            output, provide a single comprehensive response that addresses all the
            changes rather than responding to each line individually.
            """
        ).strip()
        self.client = AsyncClient()
        self.model = model
        self.quick = quick
        self.command_mode = command_mode
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.last_thinking: str | None = None

    async def send_prompt(
        self, prompt: str | None = None, code: str | None = None
    ) -> AssistantResult:
        user_content = (prompt or "").strip()

        if code:
            user_content = f"{user_content}\n\n{code}" if user_content else code

        if self.quick and user_content:
            user_content += ". Return a command and be extremely concise"

        if self.command_mode:
            instruction = (
                "Return a single bash command that accomplishes the task. "
                "Do not include explanations or formatting other than the command itself."
            )
            user_content = (
                f"{user_content}\n\n{instruction}" if user_content else instruction
            )

        user_message: Dict[str, str] = {"role": "user", "content": user_content}
        self.messages.append(user_message)

        response = await self.client.chat(
            model=self.model,
            messages=self.messages,
            stream=False,
            think=True,
        )

        assistant_message: Any | None = response.message
        if assistant_message is None:
            raise RuntimeError("No response received from the model.")

        content = getattr(assistant_message, "content", "") or ""
        thinking = getattr(assistant_message, "thinking", None)

        self.messages.append({"role": "assistant", "content": content})

        if thinking:
            self.last_thinking = thinking

        command = self._extract_command(content) if self.command_mode else None

        return AssistantResult(content=content, command=command, thinking=thinking)

    async def run_shell_command(self, command: str) -> ShellResult:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ShellResult(
            command=command,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            returncode=process.returncode or 0,
        )

    def _extract_command(self, content: str) -> str | None:
        lines = content.strip().splitlines()
        if not lines:
            return None

        command_lines: List[str] = []

        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_block:
                    break
                in_block = True
                continue
            if in_block:
                if stripped:
                    command_lines = [stripped]
                    break
                continue
            if stripped:
                command_lines = [stripped]
                break

        if not command_lines:
            return None

        command = command_lines[0]
        first_semicolon = command.find(";")
        if first_semicolon != -1:
            command = command[:first_semicolon].strip()

        return command or None


class InlineInterface:
    def __init__(
        self,
        assistant: RubberDuck,
        logger: ConversationLogger | None = None,
        code: str | None = None,
    ) -> None:
        ensure_history_dir()
        self.assistant = assistant
        self.logger = logger
        self.last_command: str | None = None
        self.code = code
        self._code_sent = False
        self.session: PromptSession | None = None

        if (
            PromptSession is not None
            and FileHistory is not None
            and KeyBindings is not None
        ):
            self.session = PromptSession(
                message=">> ",
                multiline=True,
                history=FileHistory(str(PROMPT_HISTORY_FILE)),
                key_bindings=self._create_key_bindings(),
            )

    def _create_key_bindings(self) -> KeyBindings | None:
        if KeyBindings is None:  # pragma: no cover - fallback mode
            return None

        kb = KeyBindings()

        @kb.add("enter")
        def _(event) -> None:
            buffer = event.current_buffer
            buffer.validate_and_handle()

        @kb.add("c-j")
        def _(event) -> None:
            event.current_buffer.insert_text("\n")

        @kb.add("c-r")
        def _(event) -> None:
            event.app.exit(result="__RUN_LAST__")

        return kb

    async def run(self) -> None:
        if self.session is None:
            console.print(
                "prompt_toolkit not installed. Falling back to basic input (no history/shortcuts).",
                style="yellow",
            )
            await self._run_basic_loop()
            return

        console.print(
            "Enter submits • Ctrl+J inserts newline • Ctrl+R reruns last command • '!cmd' runs shell • Ctrl+D exits",
            style="dim",
        )
        while True:
            try:
                with patch_stdout():
                    text = await self.session.prompt_async()
            except EOFError:
                console.print()
                console.print("Exiting.", style="dim")
                return
            except KeyboardInterrupt:
                console.print()
                console.print("Interrupted. Press Ctrl+D to exit.", style="yellow")
                continue

            if text == "__RUN_LAST__":
                await self._run_last_command()
                continue

            await self._process_text(text)

    async def _run_last_command(self) -> None:
        if not self.last_command:
            console.print("No suggested command available yet.", style="yellow")
            return
        await run_shell_and_print(self.assistant, self.last_command, logger=self.logger)

    async def _process_text(self, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            return

        if stripped.lower() in {":run", "/run"}:
            await self._run_last_command()
            return

        if stripped.startswith("!"):
            await run_shell_and_print(
                self.assistant, stripped[1:].strip(), logger=self.logger
            )
            return

        result = await run_single_prompt(
            self.assistant,
            stripped,
            code=self.code if not self._code_sent else None,
            logger=self.logger,
        )
        if self.code and not self._code_sent:
            self._code_sent = True
        self.last_command = result.command

    async def _run_basic_loop(self) -> None:  # pragma: no cover - fallback path
        while True:
            try:
                text = await asyncio.to_thread(input, ">> ")
            except EOFError:
                console.print()
                console.print("Exiting.", style="dim")
                return
            except KeyboardInterrupt:
                console.print()
                console.print("Interrupted. Press Ctrl+D to exit.", style="yellow")
                continue

            await self._process_text(text)


def read_files_from_dir(directory: str) -> str:
    import os

    files = os.listdir(directory)
    code = ""
    for file in files:
        full_path = f"{directory}/{file}"
        if not os.path.isfile(full_path):
            continue
        with open(full_path, "r", encoding="utf-8", errors="ignore") as handle:
            code += handle.read()
    return code


async def run_single_prompt(
    rubber_ducky: RubberDuck,
    prompt: str,
    code: str | None = None,
    logger: ConversationLogger | None = None,
) -> AssistantResult:
    if logger:
        logger.log_user(prompt)
    result = await rubber_ducky.send_prompt(prompt=prompt, code=code)
    content = result.content or "(No content returned.)"
    console.print(content, style="green", highlight=False)
    if logger:
        logger.log_assistant(content, result.command)
    if result.command:
        console.print("\nSuggested command:", style="cyan", highlight=False)
        console.print(result.command, style="bold cyan", highlight=False)
    return result


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        choice = input(prompt + suffix)
    except EOFError:
        return default
    choice = choice.strip().lower()
    if not choice:
        return default
    return choice in {"y", "yes"}


async def interactive_session(
    rubber_ducky: RubberDuck,
    logger: ConversationLogger | None = None,
    code: str | None = None,
) -> None:
    ui = InlineInterface(rubber_ducky, logger=logger, code=code)
    await ui.run()


async def ducky() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", "-d", help="The directory to be processed", default=None
    )
    parser.add_argument(
        "--model", "-m", help="The model to be used", default="qwen3-coder:480b-cloud"
    )
    args, _ = parser.parse_known_args()

    ensure_history_dir()
    logger = ConversationLogger(CONVERSATION_LOG_FILE)
    rubber_ducky = RubberDuck(model=args.model, quick=False, command_mode=True)

    code = read_files_from_dir(args.directory) if args.directory else None

    piped_prompt: str | None = None
    if not sys.stdin.isatty():
        piped_prompt = sys.stdin.read()
        piped_prompt = piped_prompt.strip() or None

    if piped_prompt is not None:
        if piped_prompt:
            result = await run_single_prompt(
                rubber_ducky, piped_prompt, code=code, logger=logger
            )
            if (
                result.command
                and sys.stdout.isatty()
                and confirm("Run suggested command?")
            ):
                await run_shell_and_print(
                    rubber_ducky, result.command, logger=logger
                )
        else:
            console.print("No input received from stdin.", style="yellow")
        return

    await interactive_session(rubber_ducky, logger=logger, code=code)


def main() -> None:
    asyncio.run(ducky())


if __name__ == "__main__":
    main()
