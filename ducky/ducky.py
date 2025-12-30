from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import signal
from dataclasses import dataclass
from datetime import UTC, datetime
from rich.console import Console
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List


@dataclass
class Crumb:
    name: str
    path: Path
    type: str
    enabled: bool
    description: str | None = None
    poll: bool = False
    poll_type: str | None = None  # "interval" or "continuous"
    poll_interval: int = 2
    poll_prompt: str | None = None


from contextlib import nullcontext

from ollama import AsyncClient

from .config import ConfigManager

try:  # prompt_toolkit is optional at runtime
    from prompt_toolkit import PromptSession
    from prompt_toolkit.application import Application
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.patch_stdout import patch_stdout
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Box, Button, Dialog, Label, TextArea
except ImportError:  # pragma: no cover - fallback mode
    PromptSession = None  # type: ignore[assignment]
    FileHistory = None  # type: ignore[assignment]
    KeyBindings = None  # type: ignore[assignment]

    def patch_stdout() -> nullcontext:
        return nullcontext()


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
CRUMBS_DIR = HISTORY_DIR / "crumbs"
CRUMBS: Dict[str, Crumb] = {}
console = Console()


def ensure_history_dir() -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    CRUMBS_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def load_crumbs() -> Dict[str, Crumb]:
    """Populate the global ``CRUMBS`` dictionary from both default and user crumbs.

    Each crumb is expected to be a directory containing an ``info.txt`` and a
    script file matching the ``type`` field (``shell`` → ``*.sh``).

    Default crumbs are loaded from the package directory first, then user crumbs
    are loaded from ``~/.ducky/crumbs/`` and can override default crumbs if they
    have the same name.
    """

    global CRUMBS
    CRUMBS.clear()

    # Helper function to load crumbs from a directory
    def _load_from_dir(dir_path: Path) -> None:
        if not dir_path.exists():
            return

        for crumb_dir in dir_path.iterdir():
            if not crumb_dir.is_dir():
                continue
            info_path = crumb_dir / "info.txt"
            if not info_path.is_file():
                continue
            # Parse key: value pairs
            meta = {}
            for line in info_path.read_text(encoding="utf-8").splitlines():
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip()
            name = meta.get("name", crumb_dir.name)
            ctype = meta.get("type", "shell")
            description = meta.get("description")
            poll = meta.get("poll", "").lower() == "true"
            poll_type = meta.get("poll_type")
            poll_interval = int(meta.get("poll_interval", 2))
            poll_prompt = meta.get("poll_prompt")
            # Find script file: look for executable in the directory
            script_path: Path | None = None
            if ctype == "shell":
                # Prefer a file named <name>.sh if present
                candidate = crumb_dir / f"{name}.sh"
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    script_path = candidate
                else:
                    # Fallback: first .sh in dir
                    for p in crumb_dir.glob("*.sh"):
                        if os.access(p, os.X_OK):
                            script_path = p
                            break
            # Default to first file if script not found
            if script_path is None:
                files = list(crumb_dir.iterdir())
                if files:
                    script_path = files[0]
            if script_path is None:
                continue
            crumb = Crumb(
                name=name,
                path=script_path,
                type=ctype,
                enabled=False,
                description=description,
                poll=poll,
                poll_type=poll_type,
                poll_interval=poll_interval,
                poll_prompt=poll_prompt,
            )
            CRUMBS[name] = crumb

    # Try to load from package directory (where ducky is installed)
    try:
        # Try to locate the crumbs directory relative to the ducky package
        import ducky
        # Get the directory containing the ducky package
        ducky_dir = Path(ducky.__file__).parent
        # Check if crumbs exists in the same directory as ducky package
        default_crumbs_dir = ducky_dir.parent / "crumbs"
        if default_crumbs_dir.exists():
            _load_from_dir(default_crumbs_dir)
    except Exception:
        # If package directory loading fails, continue without default crumbs
        pass

    # Load user crumbs (these can override default crumbs with the same name)
    _load_from_dir(CRUMBS_DIR)

    return CRUMBS


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
        entry["timestamp"] = datetime.now(UTC).isoformat()
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
    history: list[dict[str, str]] | None = None,
) -> None:
    if not command:
        console.print("No command provided.", style="yellow")
        return
    console.print(f"$ {command}", style="bold magenta")
    result = await assistant.run_shell_command(command)
    print_shell_result(result)
    if logger:
        logger.log_shell(result)
    if history is not None:
        history.append({"role": "user", "content": f"!{command}"})
        combined_output: list[str] = []
        if result.stdout.strip():
            combined_output.append(result.stdout.rstrip())
        if result.stderr.strip():
            combined_output.append(f"[stderr]\n{result.stderr.rstrip()}")
        if result.returncode != 0:
            combined_output.append(f"(exit status {result.returncode})")
        if not combined_output:
            combined_output.append("(command produced no output)")
        history.append({"role": "assistant", "content": "\n\n".join(combined_output)})


class RubberDuck:
    def __init__(
        self,
        model: str,
        quick: bool = False,
        command_mode: bool = False,
        host: str = "",
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

        # Set OLLAMA_HOST based on whether it's a cloud model
        if host:
            os.environ["OLLAMA_HOST"] = host
        elif "-cloud" in model:
            os.environ["OLLAMA_HOST"] = "https://ollama.com"
        elif "OLLAMA_HOST" not in os.environ:
            # Default to localhost if not set and not a cloud model
            os.environ["OLLAMA_HOST"] = "http://localhost:11434"

        self.client = AsyncClient()
        self.model = model
        self.quick = quick
        self.command_mode = command_mode
        self.crumbs = load_crumbs()
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        # Update system prompt to include enabled crumb descriptions

    def update_system_prompt(self) -> None:
        """Append enabled crumb descriptions to the system prompt.

        The system prompt is stored in ``self.system_prompt`` and injected as the
        first system message. When crumbs are enabled, we add a section that
        lists the crumb names and their descriptions. The format is simple:

        ``Crumbs:``\n
        ``- <name>: <description>``\n
        If no crumbs are enabled the prompt is unchanged.
        """
        # Start with the base system prompt
        prompt_lines = [self.system_prompt]

        if self.crumbs:
            prompt_lines.append(
                "\nCrumbs are simple scripts you can run with bash, uv, or bun."
            )
            prompt_lines.append("Crumbs:")
            for c in self.crumbs.values():
                description = c.description or "no description"
                prompt_lines.append(f"- {c.name}: {description}")

        # Update the system prompt
        self.system_prompt = "\n".join(prompt_lines)

        # Update the first system message in the messages list
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = self.system_prompt
        else:
            # If there's no system message, add one
            self.messages.insert(0, {"role": "system", "content": self.system_prompt})

    async def send_prompt(
        self, prompt: str | None = None, code: str | None = None, command_mode: bool | None = None
    ) -> AssistantResult:
        user_content = (prompt or "").strip()

        self.update_system_prompt()

        if code:
            user_content = f"{user_content}\n\n{code}" if user_content else code

        if self.quick and user_content:
            user_content += ". Return a command and be extremely concise"

        # Use provided command_mode, or fall back to self.command_mode
        effective_command_mode = command_mode if command_mode is not None else self.command_mode

        if effective_command_mode:
            instruction = (
                "Return a single bash command that accomplishes the task. Unless user wants something els"
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
            think=False,
        )

        assistant_message: Any | None = response.message
        if assistant_message is None:
            raise RuntimeError("No response received from the model.")

        content = getattr(assistant_message, "content", "") or ""
        thinking = getattr(assistant_message, "thinking", None)

        self.messages.append({"role": "assistant", "content": content})

        if thinking:
            self.last_thinking = thinking

        command = self._extract_command(content) if effective_command_mode else None

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

    async def list_models(self, host: str = "") -> list[str]:
        """List available Ollama models."""
        # Set the host temporarily for this operation
        original_host = os.environ.get("OLLAMA_HOST", "")
        if host:
            os.environ["OLLAMA_HOST"] = host
            self.client = AsyncClient(host)
        try:
            response = await self.client.list()
            models = []
            for m in response.models:
                models.append(m.model)
            return models
        except Exception as e:
            console.print(f"Error listing models: {e}", style="red")
            return []
        finally:
            # Restore original host
            if original_host:
                os.environ["OLLAMA_HOST"] = original_host
                self.client = AsyncClient(original_host)
            elif "OLLAMA_HOST" in os.environ:
                del os.environ["OLLAMA_HOST"]
                self.client = AsyncClient()

    def switch_model(self, model_name: str, host: str = "") -> None:
        """Switch to a different Ollama model."""
        self.model = model_name

        # Set the host based on the model or explicit host
        if host:
            os.environ["OLLAMA_HOST"] = host
            self.client = AsyncClient(host)
        elif "-cloud" in model_name:
            os.environ["OLLAMA_HOST"] = "https://ollama.com"
            self.client = AsyncClient("https://ollama.com")
        else:
            os.environ["OLLAMA_HOST"] = "http://localhost:11434"
            self.client = AsyncClient()

        console.print(f"Switched to model: {model_name}", style="green")

    def clear_history(self) -> None:
        """Reset conversation history to the initial system prompt."""
        if self.messages:
            self.messages = [self.messages[0]]
        console.print("Conversation history cleared.", style="green")


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
        self.last_shell_output: str | None = None
        self.pending_command: str | None = None
        self.session: PromptSession | None = None
        self.selected_model: str | None = None
        self.running_polling: bool = False

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

        @kb.add("c-s")
        def _(event) -> None:
            # This will be handled in the processing loop
            event.app.exit(result="__COPY_LAST__")

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
            "Enter submits • empty Enter reruns the last suggested command (or explains the last shell output) • '!<cmd>' runs shell • Ctrl+D exits • Ctrl+S copies last command",
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
            except (KeyboardInterrupt, asyncio.CancelledError):
                console.print()
                console.print("Interrupted. Press Ctrl+D to exit.", style="yellow")
                continue

            if text == "__RUN_LAST__":
                await self._run_last_command()
                continue

            if text == "__COPY_LAST__":
                await self._copy_last_command()
                continue

            await self._process_text(text)

    async def _copy_last_command(self) -> None:
        """Copy the last suggested command to clipboard."""
        if not self.last_command:
            console.print("No suggested command available to copy.", style="yellow")
            return

        try:
            import subprocess
            import platform

            command_to_copy = self.last_command

            system = platform.system()
            if system == "Darwin":  # macOS
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
                process.communicate(input=command_to_copy)
            elif system == "Windows":
                process = subprocess.Popen(["clip"], stdin=subprocess.PIPE, text=True)
                process.communicate(input=command_to_copy)
            else:  # Linux and others
                # Try xclip first, then xsel as fallback
                try:
                    process = subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        stdin=subprocess.PIPE,
                        text=True,
                    )
                    process.communicate(input=command_to_copy)
                except FileNotFoundError:
                    # Try xsel as fallback
                    process = subprocess.Popen(
                        ["xsel", "-b", "-i"], stdin=subprocess.PIPE, text=True
                    )
                    process.communicate(input=command_to_copy)

            console.print(f"Copied to clipboard: {command_to_copy}", style="green")
        except Exception as e:
            console.print(f"Failed to copy to clipboard: {e}", style="red")
            console.print("You can manually copy the last command:", style="dim")
            console.print(f"  {self.last_command}", style="bold")

    async def _run_last_command(self) -> None:
        if not self.last_command:
            console.print("No suggested command available yet.", style="yellow")
            return
        await run_shell_and_print(
            self.assistant,
            self.last_command,
            logger=self.logger,
            history=self.assistant.messages,
        )
        # Add the command to prompt history so user can recall it with up arrow
        if self.session and self.session.history and self.last_command:
            self.session.history.append_string(self.last_command)
        self.last_shell_output = True
        self.pending_command = None
        self.last_command = None

    async def _process_text(self, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            if self.pending_command:
                await self._run_last_command()
                return
            if self.last_shell_output:
                await self._explain_last_command()
                return
            console.print("Nothing to run yet.", style="yellow")
            return

        if stripped.lower() in {":run", "/run"}:
            await self._run_last_command()
            return

        if stripped.lower() in {"/clear", "/reset"}:
            await self._clear_history()
            return

        if stripped.lower() == "/model":
            await self._select_model()
            return

        if stripped.lower() == "/local":
            await self._select_model(host="http://localhost:11434")
            return

        if stripped.lower() == "/cloud":
            await self._select_model(host="https://ollama.com")
            return

        if stripped.lower() == "/help":
            await self._show_help()
            return

        if stripped.lower() == "/crumbs":
            await self._show_crumbs()
            return

        if stripped.lower() == "/stop-poll":
            await self._stop_polling()
            return

        if stripped.startswith("/poll"):
            await self._handle_poll_command(stripped)
            return

        if stripped.startswith("!"):
            command = stripped[1:].strip()
            await run_shell_and_print(
                self.assistant,
                command,
                logger=self.logger,
                history=self.assistant.messages,
            )
            # Add the command to prompt history so user can recall it with up arrow
            if self.session and self.session.history and command:
                self.session.history.append_string(command)
            self.last_shell_output = True
            self.pending_command = None
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
        self.pending_command = result.command

    async def _explain_last_command(self) -> None:
        if not self.assistant.messages or len(self.assistant.messages) < 2:
            console.print("No shell output to explain yet.", style="yellow")
            return
        last_entry = self.assistant.messages[-1]
        if last_entry["role"] != "assistant":
            console.print("No shell output to explain yet.", style="yellow")
            return
        prompt = (
            "The user ran a shell command above. Summarize the key findings from the output, "
            "highlight problems if any, and suggest next steps. Do NOT suggest a shell command or code snippet.\n\n"
            f"{last_entry['content']}"
        )
        await run_single_prompt(
            self.assistant, prompt, logger=self.logger, suppress_suggestion=True
        )
        self.last_shell_output = None

    async def _show_help(self) -> None:
        """Display help information for all available commands."""
        console.print("\nDucky CLI Help", style="bold blue")
        console.print("===============", style="bold blue")
        console.print()

        commands = [
            ("[bold]/help[/bold]", "Show this help message"),
            ("[bold]/crumbs[/bold]", "List all available crumbs"),
            ("[bold]/model[/bold]", "Select a model interactively (local or cloud)"),
            (
                "[bold]/local[/bold]",
                "List and select from local models (localhost:11434)",
            ),
            ("[bold]/cloud[/bold]", "List and select from cloud models (ollama.com)"),
            (
                "[bold]/clear[/bold] or [bold]/reset[/bold]",
                "Clear conversation history",
            ),
            (
                "[bold]/poll <crumb>[/bold]",
                "Start polling session for a crumb",
            ),
            (
                "[bold]/poll <crumb> -i 5[/bold]",
                "Start polling with 5s interval",
            ),
            (
                "[bold]/poll <crumb> -p <text>[/bold]",
                "Start polling with custom prompt",
            ),
            (
                "[bold]/stop-poll[/bold]",
                "Stop current polling session",
            ),
            (
                "[bold]/run[/bold]",
                "Re-run the last suggested command",
            ),
            (
                "[bold]Empty Enter[/bold]",
                "Re-run suggested command or explain last output",
            ),
            ("[bold]![<command>][/bold]", "Execute a shell command directly"),
            ("[bold]Ctrl+D[/bold]", "Exit the application"),
            ("[bold]Ctrl+R[/bold]", "Re-run the last suggested command"),
            ("[bold]Ctrl+S[/bold]", "Copy the last suggested command to clipboard"),
        ]

        for command, description in commands:
            console.print(f"{command:<45} {description}")

        console.print()

    async def _show_crumbs(self) -> None:
        """Display all available crumbs."""
        crumbs = self.assistant.crumbs

        if not crumbs:
            console.print("No crumbs available.", style="yellow")
            return

        console.print("\nAvailable Crumbs", style="bold blue")
        console.print("===============", style="bold blue")
        console.print()

        # Group crumbs by source (default vs user)
        default_crumbs = []
        user_crumbs = []

        for name, crumb in sorted(crumbs.items()):
            path_str = str(crumb.path)
            if "crumbs/" in path_str and "/.ducky/crumbs/" not in path_str:
                default_crumbs.append((name, crumb))
            else:
                user_crumbs.append((name, crumb))

        # Show default crumbs
        if default_crumbs:
            console.print("[bold cyan]Default Crumbs (shipped with ducky):[/bold cyan]", style="cyan")
            for name, crumb in default_crumbs:
                description = crumb.description or "No description"
                # Check if it has polling enabled
                poll_info = " [dim](polling enabled)[/dim]" if crumb.poll else ""
                console.print(f"  [bold]{name}[/bold]{poll_info}: {description}")
            console.print()

        # Show user crumbs
        if user_crumbs:
            console.print("[bold green]Your Crumbs:[/bold green]", style="green")
            for name, crumb in user_crumbs:
                description = crumb.description or "No description"
                # Check if it has polling enabled
                poll_info = " [dim](polling enabled)[/dim]" if crumb.poll else ""
                console.print(f"  [bold]{name}[/bold]{poll_info}: {description}")
            console.print()

        console.print(f"[dim]Total: {len(crumbs)} crumbs available[/dim]")

    async def _clear_history(self) -> None:
        self.assistant.clear_history()
        self.last_command = None
        self.pending_command = None
        self.last_shell_output = None

    async def _handle_poll_command(self, command: str) -> None:
        """Handle /poll command with optional arguments."""
        if self.running_polling:
            console.print(
                "A polling session is already running. Use /stop-poll first.",
                style="yellow",
            )
            return

        # Parse command: /poll <crumb> [-i interval] [-p prompt]
        parts = command.split()
        if len(parts) < 2:
            console.print("Usage: /poll <crumb-name> [-i interval] [-p prompt]", style="yellow")
            console.print("Example: /poll log-crumb -i 5", style="dim")
            return

        crumb_name = parts[1]
        interval = None
        prompt = None

        # Parse optional arguments
        i = 2
        while i < len(parts):
            if parts[i] in {"-i", "--interval"} and i + 1 < len(parts):
                try:
                    interval = int(parts[i + 1])
                    i += 2
                except ValueError:
                    console.print("Invalid interval value.", style="red")
                    return
            elif parts[i] in {"-p", "--prompt"} and i + 1 < len(parts):
                prompt = " ".join(parts[i + 1:])
                break
            else:
                i += 1

        if crumb_name not in self.assistant.crumbs:
            console.print(f"Crumb '{crumb_name}' not found.", style="red")
            console.print(
                f"Available crumbs: {', '.join(self.assistant.crumbs.keys())}",
                style="yellow",
            )
            return

        crumb = self.assistant.crumbs[crumb_name]

        if not crumb.poll:
            console.print(
                f"Warning: Crumb '{crumb_name}' doesn't have polling enabled.",
                style="yellow",
            )
            console.print("Proceeding anyway with default polling mode.", style="dim")

        console.print("Starting polling session... Press Ctrl+C to stop.", style="bold cyan")

        self.running_polling = True
        try:
            await polling_session(
                self.assistant,
                crumb,
                interval=interval,
                prompt_override=prompt,
            )
        finally:
            self.running_polling = False
            console.print("Polling stopped. Returning to interactive mode.", style="green")

    async def _stop_polling(self) -> None:
        """Handle /stop-poll command."""
        if not self.running_polling:
            console.print("No polling session is currently running.", style="yellow")
            return

        # This is handled by the signal handler in polling_session
        console.print(
            "Stopping polling... (press Ctrl+C if it doesn't stop automatically)",
            style="yellow",
        )

    async def _select_model(self, host: str = "") -> None:
        """Show available models and allow user to select one with arrow keys."""
        if PromptSession is None or KeyBindings is None:
            console.print(
                "Model selection requires prompt_toolkit to be installed.",
                style="yellow",
            )
            return

        # Show current model
        console.print(f"Current model: {self.assistant.model}", style="bold green")

        # If no host specified, give user a choice between local and cloud
        if not host:
            console.print("\nSelect model type:", style="bold")
            console.print("1. Local models (localhost:11434)")
            console.print("2. Cloud models (ollama.com)")
            console.print("Press Esc to cancel", style="dim")

            try:
                choice = await asyncio.to_thread(input, "Enter choice (1 or 2): ")
                choice = choice.strip()

                if choice.lower() == "esc":
                    console.print("Model selection cancelled.", style="yellow")
                    return

                if choice == "1":
                    host = "http://localhost:11434"
                elif choice == "2":
                    host = "https://ollama.com"
                else:
                    console.print("Invalid choice. Please select 1 or 2.", style="red")
                    return
            except (ValueError, EOFError):
                console.print("Invalid input.", style="red")
                return

        models = await self.assistant.list_models(host)
        if not models:
            if host == "http://localhost:11434":
                console.print(
                    "No local models available. Is Ollama running?", style="red"
                )
                console.print("Start Ollama with: ollama serve", style="yellow")
            else:
                console.print("No models available.", style="yellow")
            return

        if host == "https://ollama.com":
            console.print("\nAvailable cloud models:", style="bold")
        elif host == "http://localhost:11434":
            console.print("\nAvailable local models:", style="bold")
        else:
            console.print("\nAvailable models:", style="bold")

        for i, model in enumerate(models, 1):
            if model == self.assistant.model:
                console.print(f"{i}. {model} (current)", style="green")
            else:
                console.print(f"{i}. {model}")

        console.print("Press Esc to cancel", style="dim")
        try:
            choice = await asyncio.to_thread(input, "Enter model number or name: ")
            choice = choice.strip()

            if choice.lower() == "esc":
                console.print("Model selection cancelled.", style="yellow")
                return

            # Check if it's a number
            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(models):
                    selected_model = models[index]
                else:
                    console.print("Invalid model number.", style="red")
                    return
            else:
                # Check if it's a model name
                if choice in models:
                    selected_model = choice
                else:
                    console.print("Invalid model name.", style="red")
                    return

            self.assistant.switch_model(selected_model, host)

            # Save the selected model and host to config
            config_manager = ConfigManager()
            config_manager.save_last_model(
                selected_model,
                host or os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            )
        except (ValueError, EOFError):
            console.print("Invalid input.", style="red")

    async def _run_basic_loop(self) -> None:  # pragma: no cover - fallback path
        while True:
            try:
                text = await asyncio.to_thread(input, ">> ")
            except EOFError:
                console.print()
                console.print("Exiting.", style="dim")
                return
            except (KeyboardInterrupt, asyncio.CancelledError):
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
    suppress_suggestion: bool = False,
) -> AssistantResult:
    if logger:
        logger.log_user(prompt)
    result = await rubber_ducky.send_prompt(prompt=prompt, code=code)
    content = result.content or "(No content returned.)"
    console.print(content, style="green", highlight=False)
    if logger:
        logger.log_assistant(content, result.command)
    if result.command and not suppress_suggestion:
        console.print("\nSuggested command:", style="cyan", highlight=False)
        console.print(result.command, style="bold cyan", highlight=False)
    return result


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard using pbcopy on macOS."""
    try:
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))
        return process.returncode == 0
    except Exception:
        return False


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


async def polling_session(
    rubber_ducky: RubberDuck,
    crumb: Crumb,
    interval: int | None = None,
    prompt_override: str | None = None,
) -> None:
    """Run a polling session for a crumb.

    For interval polling: Runs the crumb repeatedly at the specified interval.
    For continuous polling: Runs the crumb once in background and analyzes output periodically.

    Args:
        rubber_ducky: The RubberDuck assistant
        crumb: The crumb to poll
        interval: Override the crumb's default interval
        prompt_override: Override the crumb's default poll prompt
    """
    # Use overrides or crumb defaults
    poll_interval = interval or crumb.poll_interval
    poll_prompt = prompt_override or crumb.poll_prompt or "Analyze this output."
    poll_type = crumb.poll_type or "interval"

    if not crumb.poll_prompt and not prompt_override:
        console.print("Warning: No poll prompt configured for this crumb.", style="yellow")
        console.print(f"Using default prompt: '{poll_prompt}'", style="dim")

    if poll_type == "continuous":
        await _continuous_polling(rubber_ducky, crumb, poll_interval, poll_prompt)
    else:
        await _interval_polling(rubber_ducky, crumb, poll_interval, poll_prompt)


async def _interval_polling(
    rubber_ducky: RubberDuck,
    crumb: Crumb,
    interval: int,
    poll_prompt: str,
) -> None:
    """Poll by running crumb script at intervals and analyzing with AI."""
    console.print(
        f"\nStarting interval polling for '{crumb.name}' (interval: {interval}s)...\n"
        f"Poll prompt: {poll_prompt}\n"
        f"Press Ctrl+C to stop polling.\n",
        style="bold cyan",
    )

    shutdown_event = asyncio.Event()

    def signal_handler():
        console.print("\nStopping polling...", style="yellow")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    try:
        while not shutdown_event.is_set():
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"\n[{timestamp}] Polling {crumb.name}...", style="bold blue")

            # Run crumb script
            result = await rubber_ducky.run_shell_command(str(crumb.path))

            script_output = result.stdout if result.stdout.strip() else "(no output)"
            if result.stderr.strip():
                script_output += f"\n[stderr]\n{result.stderr}"

            console.print(f"Script output: {len(result.stdout)} bytes\n", style="dim")

            # Send to AI with prompt
            full_prompt = f"{poll_prompt}\n\nScript output:\n{script_output}"
            ai_result = await rubber_ducky.send_prompt(prompt=full_prompt, command_mode=False)

            console.print(f"AI: {ai_result.content}", style="green", highlight=False)

            # Wait for next interval
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        console.print("\nPolling stopped.", style="yellow")
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def _continuous_polling(
    rubber_ducky: RubberDuck,
    crumb: Crumb,
    interval: int,
    poll_prompt: str,
) -> None:
    """Poll by running crumb continuously and analyzing output periodically."""
    console.print(
        f"\nStarting continuous polling for '{crumb.name}' (analysis interval: {interval}s)...\n"
        f"Poll prompt: {poll_prompt}\n"
        f"Press Ctrl+C to stop polling.\n",
        style="bold cyan",
    )

    shutdown_event = asyncio.Event()
    accumulated_output: list[str] = []

    def signal_handler():
        console.print("\nStopping polling...", style="yellow")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    # Start crumb process
    process = None
    try:
        process = await asyncio.create_subprocess_shell(
            str(crumb.path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read_stream(stream, name: str):
            """Read output from stream non-blocking."""
            while not shutdown_event.is_set():
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=0.1)
                    if not line:
                        break
                    line_text = line.decode(errors="replace")
                    accumulated_output.append(line_text)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

        # Read both stdout and stderr
        asyncio.create_task(read_stream(process.stdout, "stdout"))
        asyncio.create_task(read_stream(process.stderr, "stderr"))

        # Main polling loop - analyze accumulated output
        last_analyzed_length = 0

        while not shutdown_event.is_set():
            await asyncio.sleep(interval)

            # Only analyze if there's new output
            current_length = len(accumulated_output)
            if current_length > last_analyzed_length:
                timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                console.print(f"\n[{timestamp}] Polling {crumb.name}...", style="bold blue")

                # Get new output since last analysis
                new_output = "".join(accumulated_output[last_analyzed_length:])

                console.print(f"New script output: {len(new_output)} bytes\n", style="dim")

                # Send to AI with prompt
                full_prompt = f"{poll_prompt}\n\nScript output:\n{new_output}"
                ai_result = await rubber_ducky.send_prompt(prompt=full_prompt, command_mode=False)

                console.print(f"AI: {ai_result.content}", style="green", highlight=False)

                last_analyzed_length = current_length

    except asyncio.CancelledError:
        console.print("\nPolling stopped.", style="yellow")
    finally:
        if process:
            process.kill()
            await process.wait()
        loop.remove_signal_handler(signal.SIGINT)


async def ducky() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", "-d", help="The directory to be processed", default=None
    )
    parser.add_argument("--model", "-m", help="The model to be used", default=None)
    parser.add_argument(
        "--local",
        "-l",
        action="store_true",
        help="Run DuckY offline using a local Ollama instance on localhost:11434",
    )
    parser.add_argument(
        "--poll",
        help="Start polling mode for the specified crumb",
        default=None,
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        help="Override crumb's polling interval in seconds",
        default=None,
    )
    parser.add_argument(
        "--prompt",
        "-p",
        help="Override crumb's polling prompt",
        default=None,
    )
    parser.add_argument(
        "single_prompt",
        nargs="?",
        help="Run a single prompt and copy the suggested command to clipboard",
        default=None,
    )
    args = parser.parse_args()

    ensure_history_dir()
    logger = ConversationLogger(CONVERSATION_LOG_FILE)

    # Load the last used model from config if no model is specified
    config_manager = ConfigManager()
    last_model, last_host = config_manager.get_last_model()

    # If --local flag is used, override with local settings
    if getattr(args, "local", False):
        # Point Ollama client to local host and use gemma3 as default model
        os.environ["OLLAMA_HOST"] = "http://localhost:11434"
        args.model = args.model or "gemma2:9b"
        last_host = "http://localhost:11434"
    # If no model is specified, use the last used model
    elif args.model is None:
        args.model = last_model
        # Set the host based on the last used host
        if last_host:
            os.environ["OLLAMA_HOST"] = last_host

    rubber_ducky = RubberDuck(
        model=args.model, quick=False, command_mode=True, host=last_host
    )

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
                    rubber_ducky,
                    result.command,
                    logger=logger,
                    history=rubber_ducky.messages,
                )
        else:
            console.print("No input received from stdin.", style="yellow")
        return

    # Handle single prompt mode
    if args.single_prompt:
        result = await run_single_prompt(
            rubber_ducky, args.single_prompt, code=code, logger=logger
        )
        if result.command:
            if copy_to_clipboard(result.command):
                console.print("\n[green]✓[/green] Command copied to clipboard")
        return

    # Handle polling mode
    if args.poll:
        crumb_name = args.poll
        if crumb_name not in rubber_ducky.crumbs:
            console.print(f"Crumb '{crumb_name}' not found.", style="red")
            console.print(
                f"Available crumbs: {', '.join(rubber_ducky.crumbs.keys())}",
                style="yellow",
            )
            return

        crumb = rubber_ducky.crumbs[crumb_name]
        if not crumb.poll:
            console.print(
                f"Warning: Crumb '{crumb_name}' doesn't have polling enabled.",
                style="yellow",
            )
            console.print("Proceeding anyway with default polling mode.", style="dim")

        await polling_session(
            rubber_ducky,
            crumb,
            interval=args.interval,
            prompt_override=args.prompt,
        )
        return

    await interactive_session(rubber_ducky, logger=logger, code=code)


def main() -> None:
    asyncio.run(ducky())


if __name__ == "__main__":
    main()
