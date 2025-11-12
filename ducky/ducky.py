import argparse
import asyncio
import sys
from textwrap import dedent
from typing import Any, Dict, List

from ollama import AsyncClient

try:
    import readline
except ImportError:  # pragma: no cover - readline not available on some platforms
    readline = None


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
        self.prompt_history: List[str] = []

    async def call_llm(
        self, prompt: str | None = None, code: str | None = None
    ) -> None:
        interactive = prompt is None and code is None

        if prompt is None:
            if interactive:
                prompt = input(
                    "\nEnter your prompt (or press Enter for default review): "
                )
            else:
                prompt = ""

        if prompt:
            self._remember_prompt(prompt)

        pending_code = code

        while True:
            if interactive:
                if not prompt:
                    prompt = self._input_with_prefill("\n>> ", "")
                    if prompt:
                        self._remember_prompt(prompt)
                    else:
                        continue

                stripped_prompt = prompt.strip()
                if stripped_prompt.startswith("!"):
                    command = stripped_prompt[1:].strip()
                    if command:
                        await self._run_shell_command(command)
                    else:
                        print("(no command provided)")
                    prompt = ""
                    continue

            user_content = prompt or ""
            if pending_code:
                if user_content:
                    user_content = f"{user_content}\n\n{pending_code}"
                else:
                    user_content = pending_code
                pending_code = None

            if self.quick and user_content:
                user_content += ". Return a command and be extremely concise"

            if self.command_mode:
                instruction = (
                    "Return a single bash command that accomplishes the task. "
                    "Do not include explanations or formatting other than the command itself."
                )
                if user_content:
                    user_content = f"{user_content}\n\n{instruction}"
                else:
                    user_content = instruction

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
                print("No response received from the model.")
                break

            content = getattr(assistant_message, "content", "") or ""
            thinking = getattr(assistant_message, "thinking", None)

            if content:
                if self.command_mode:
                    command = self._extract_command(content)
                    if command:
                        decision = self._handle_command_decision(command)
                        if decision["action"] == "run":
                            await self._run_shell_command(decision["command"])
                            content = decision["command"]
                            break
                        if decision["action"] == "reprompt":
                            prompt = decision["prompt"] or ""
                            if prompt:
                                self._remember_prompt(prompt)
                            interactive = True
                            content = command
                            continue
                    print(content)
                else:
                    print(content)
            else:
                print("(No content returned.)")

            # Store the assistant reply while keeping the hidden thinking separate.
            self.messages.append({"role": "assistant", "content": content})

            if thinking:
                # Preserve the model's internal reasoning out of band for later analysis
                # without surfacing it to the user or feeding it back into the chat.
                self.last_thinking = thinking

            if not interactive:
                break
            prompt = ""

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

        # Only keep the first command segment if multiple commands are present.
        command = command_lines[0]
        first_semicolon = command.find(";")
        if first_semicolon != -1:
            command = command[:first_semicolon].strip()

        return command or None

    def _handle_command_decision(self, command: str) -> Dict[str, str | None]:
        print("\nSuggested command:")
        print(command)

        default_prompt = self.prompt_history[-1] if self.prompt_history else ""
        try:
            follow_up = self._input_with_prefill(
                "Press Enter to run, or type a new prompt: ", default_prompt
            )
        except EOFError:
            return {"action": "cancel", "command": None, "prompt": None}

        follow_up = follow_up.strip()
        if not follow_up:
            return {"action": "run", "command": command, "prompt": None}

        if follow_up.startswith("!"):
            custom = follow_up[1:].strip() or command
            return {"action": "run", "command": custom, "prompt": None}

        return {"action": "reprompt", "command": None, "prompt": follow_up}

    async def _run_shell_command(self, command: str) -> None:
        print(f"\n$ {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if stdout:
            sys.stdout.write(stdout.decode())
        if stderr:
            sys.stderr.write(stderr.decode())
        if process.returncode != 0:
            print(f"(command exited with status {process.returncode})")

    def _input_with_prefill(self, prompt_text: str, prefill: str) -> str:
        if readline is None:
            return input(prompt_text)

        def hook() -> None:
            readline.insert_text(prefill)
            readline.redisplay()

        readline.set_pre_input_hook(hook)
        try:
            return input(prompt_text)
        finally:
            readline.set_pre_input_hook()  # reset hook

    def _remember_prompt(self, prompt: str) -> None:
        trimmed = prompt.strip()
        if not trimmed:
            return
        self.prompt_history.append(trimmed)
        if readline is not None:
            readline.add_history(trimmed)


def read_files_from_dir(directory: str) -> str:
    import os

    files = os.listdir(directory)
    code = ""
    for file in files:
        code += open(directory + "/" + file).read()
    return code


async def ducky() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question", nargs="*", help="Direct question to ask", default=None
    )
    parser.add_argument(
        "--directory", "-d", help="The directory to be processed", default=None
    )
    parser.add_argument(
        "--model", "-m", help="The model to be used", default="qwen3-coder:480b-cloud"
    )
    args, _ = parser.parse_known_args()

    rubber_ducky = RubberDuck(
        model=args.model, quick=False, command_mode=True
    )

    question = " ".join(args.question or []) or None
    prompt = question

    if args.directory:
        code = read_files_from_dir(args.directory)
        await rubber_ducky.call_llm(code=code, prompt=prompt)
        return

    await rubber_ducky.call_llm(prompt=prompt)


def main():
    asyncio.run(ducky())


if __name__ == "__main__":
    main()
