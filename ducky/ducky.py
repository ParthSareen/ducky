from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from rich.console import Console
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List

__version__ = "1.6.1"

from .config import ConfigManager
from .crumb import CrumbManager

from contextlib import nullcontext

from ollama import AsyncClient

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
CRUMBS: Dict[str, Any] = {}
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
        entry["timestamp"] = datetime.now(UTC).isoformat()
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")


def print_shell_result(result: ShellResult, truncate: bool = True) -> None:
    """Print shell command output with optional truncation.

    Args:
        result: The ShellResult containing command output
        truncate: If True and output is long (>10 lines), show truncated version
    """
    # Determine if we should truncate
    stdout_lines = result.stdout.rstrip().split('\n') if result.stdout else []
    stderr_lines = result.stderr.rstrip().split('\n') if result.stderr else []
    total_lines = len(stdout_lines) + len(stderr_lines)

    should_truncate = truncate and total_lines > 10

    if result.stdout.strip():
        if should_truncate:
            # Show first 8 lines of stdout
            show_lines = stdout_lines[:8]
            console.print('\n'.join(show_lines), highlight=False)
            console.print(f"... ({len(stdout_lines) - 8} more lines, use /expand to see full output)", style="dim cyan")
        else:
            console.print(result.stdout.rstrip(), highlight=False)

    if result.stderr.strip():
        if result.stdout.strip():
            console.print()
        console.print("[stderr]", style="bold red")
        if should_truncate:
            # Show first 5 lines of stderr
            show_lines = stderr_lines[:5]
            console.print('\n'.join(show_lines), style="red", highlight=False)
            if len(stderr_lines) > 5:
                console.print(f"... ({len(stderr_lines) - 5} more lines)", style="dim red")
        else:
            console.print(result.stderr.rstrip(), style="red", highlight=False)

    if result.returncode != 0 or (not result.stdout.strip() and not result.stderr.strip()):
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
) -> ShellResult:
    """Run a shell command and print output. Returns the ShellResult."""
    if not command:
        console.print("No command provided.", style="yellow")
        return ShellResult(command="", stdout="", stderr="", returncode=-1)
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
    return result


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
        self.last_result: AssistantResult | None = None
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]

    async def send_prompt(
        self, prompt: str | None = None, code: str | None = None, command_mode: bool | None = None
    ) -> AssistantResult:
        user_content = (prompt or "").strip()

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

        result = AssistantResult(content=content, command=command, thinking=thinking)
        self.last_result = result
        return result

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
                    command_lines.append(stripped)
                continue
            if stripped:
                command_lines.append(stripped)
                # If not in a block, only take the first line
                break

        if not command_lines:
            return None

        # Join all command lines with newlines for multi-line commands
        command = "\n".join(command_lines)

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
            if "ollama.com" in host:
                console.print("[dim]Note: Cloud models require authentication[/dim]", style="yellow")
        elif "-cloud" in model_name:
            os.environ["OLLAMA_HOST"] = "https://ollama.com"
            self.client = AsyncClient("https://ollama.com")
            console.print("[dim]Note: Cloud models require authentication[/dim]", style="yellow")
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
        self.last_shell_result: ShellResult | None = None
        self.pending_command: str | None = None
        self.session: PromptSession | None = None
        self.selected_model: str | None = None
        self.crumb_manager = CrumbManager()

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
        await self._run_shell_command(self.last_command)
        # Add the command to prompt history so user can recall it with up arrow
        if self.session and self.session.history and self.last_command:
            self.session.history.append_string(self.last_command)
        self.last_shell_output = True
        self.pending_command = None
        self.last_command = None

    async def _run_shell_command(self, command: str) -> None:
        """Run a shell command, print output (with truncation), and store result."""
        result = await run_shell_and_print(
            self.assistant,
            command,
            logger=self.logger,
            history=self.assistant.messages,
        )
        # Store the result for expansion later
        self.last_shell_result = result

    async def _expand_last_output(self) -> None:
        """Expand and show the full output of the last shell command."""
        if not self.last_shell_result:
            console.print("No previous shell output to expand.", style="yellow")
            return

        console.print()
        console.print(f"[Full output for: {self.last_shell_result.command}]", style="bold cyan")
        console.print()
        print_shell_result(self.last_shell_result, truncate=False)
        console.print()

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

        # Check if first word is a crumb name
        first_word = stripped.split()[0].lower()
        if self.crumb_manager.has_crumb(first_word):
            # Extract additional arguments after the crumb name
            parts = stripped.split()
            args = parts[1:]
            await self._use_crumb(first_word, args)
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

        if stripped.startswith("/crumb"):
            await self._handle_crumb_command(stripped)
            return

        if stripped.lower() == "/expand":
            await self._expand_last_output()
            return

        if stripped.startswith("!"):
            command = stripped[1:].strip()
            await self._run_shell_command(command)
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
            ("[bold]Crumbs:[/bold]", ""),
            ("[bold]/crumb help[/bold]", "Show detailed crumb commands help"),
            ("[bold]/crumbs[/bold]", "List all saved crumb shortcuts"),
            ("[bold]/crumb <name>[/bold]", "Save last result as a crumb"),
            ("[bold]/crumb add <name> <cmd>[/bold]", "Manually add a crumb"),
            ("[bold]/crumb del <name>[/bold]", "Delete a crumb"),
            ("[bold]<name>[/bold]", "Invoke a saved crumb"),
            ("", ""),
            ("[bold]General:[/bold]", ""),
            ("[bold]/help[/bold]", "Show this help message"),
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
            ("[bold]/expand[/bold]", "Show full output of last shell command"),
            ("[bold]/run[/bold]", "Re-run the last suggested command"),
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
            if command:
                console.print(f"{command:<45} {description}")
            else:
                console.print()

        console.print()
        console.print("[dim]Use /crumb help for detailed crumb command documentation[/dim]")

        console.print()

    async def _show_crumbs(self) -> None:
        """Display all saved crumbs."""
        crumbs = self.crumb_manager.list_crumbs()

        if not crumbs:
            console.print("No crumbs saved yet. Use '/crumb <name>' to save a command.", style="yellow")
            return

        console.print("\nSaved Crumbs", style="bold blue")
        console.print("=============", style="bold blue")
        console.print()

        # Calculate max name length for alignment
        max_name_len = max(len(name) for name in crumbs.keys())

        for name, data in sorted(crumbs.items()):
            explanation = data.get("explanation", "") or "No explanation yet"
            command = data.get("command", "") or "No command"
            created_at = data.get("created_at", "")

            # Format: name | explanation | command
            console.print(
                f"[bold]{name:<{max_name_len}}[/bold] | [cyan]{explanation}[/cyan] | [dim]{command}[/dim]"
            )

        console.print(f"\n[dim]Total: {len(crumbs)} crumbs[/dim]")

    async def _clear_history(self) -> None:
        self.assistant.clear_history()
        self.last_command = None
        self.pending_command = None
        self.last_shell_output = None

    async def _handle_crumb_command(self, command: str) -> None:
        """Handle /crumb commands."""
        parts = command.split()

        if len(parts) == 1:
            # Just "/crumb" - show help
            await self._show_crumb_help()
            return

        # Check for help flag or argument
        if parts[1] in {"help", "--help", "-h"}:
            await self._show_crumb_help()
            return

        if len(parts) == 2:
            # "/crumb <name>" - save last result
            name = parts[1]
            await self._save_crumb(name)
            return

        if len(parts) >= 3 and parts[1] == "add":
            # "/crumb add <name> <...command>"
            if len(parts) < 4:
                console.print("Usage: /crumb add <name> <command>", style="yellow")
                console.print("Example: /crumb add deploy docker build -t app:latest", style="dim")
                return
            name = parts[2]
            cmd = " ".join(parts[3:])
            await self._add_crumb_manual(name, cmd)
            return

        if len(parts) == 3 and parts[1] == "del":
            # "/crumb del <name>"
            name = parts[2]
            await self._delete_crumb(name)
            return

        console.print(
            "Unknown crumb command. Use /crumb help for usage information.",
            style="yellow",
        )

    async def _show_crumb_help(self) -> None:
        """Display detailed help for crumb commands."""
        console.print("\n[bold blue]Crumbs Help[/bold blue]")
        console.print("=" * 40)
        console.print()

        console.print("[bold cyan]Commands:[/bold cyan]")
        console.print()

        commands = [
            ("[bold]/crumbs[/bold]", "List all saved crumb shortcuts"),
            ("[bold]/crumb help[/bold]", "Show this help message"),
            ("[bold]/crumb <name>[/bold]", "Save the last AI-suggested command as a crumb"),
            ("[bold]/crumb add <name> <cmd>[/bold]", "Manually add a crumb with a specific command"),
            ("[bold]/crumb del <name>[/bold]", "Delete a saved crumb"),
            ("[bold]<name>[/bold]", "Invoke a saved crumb by name"),
        ]

        for command, description in commands:
            console.print(f"{command:<45} {description}")

        console.print()
        console.print("[bold cyan]Examples:[/bold cyan]")
        console.print()
        console.print("  [dim]# List all crumbs[/dim]")
        console.print("  >> /crumbs")
        console.print()
        console.print("  [dim]# Save last command as 'deploy'[/dim]")
        console.print("  >> /crumb deploy")
        console.print()
        console.print("  [dim]# Manually add a crumb[/dim]")
        console.print("  >> /crumb add test-run pytest tests/ -v")
        console.print()
        console.print("  [dim]# Delete a crumb[/dim]")
        console.print("  >> /crumb del deploy")
        console.print()
        console.print("  [dim]# Run a saved crumb[/dim]")
        console.print("  >> test-run")
        console.print()

    async def _save_crumb(self, name: str) -> None:
        """Save the last result as a crumb."""
        if not self.assistant.last_result:
            console.print("No previous command to save. Run a command first.", style="yellow")
            return

        if not self.assistant.last_result.command:
            console.print("Last response had no command to save.", style="yellow")
            return

        # Find the last user prompt from messages
        last_prompt = ""
        for msg in reversed(self.assistant.messages):
            if msg["role"] == "user":
                last_prompt = msg["content"]
                break

        self.crumb_manager.save_crumb(
            name=name,
            prompt=last_prompt,
            response=self.assistant.last_result.content,
            command=self.assistant.last_result.command,
        )

        console.print(f"Saved crumb '{name}'!", style="green")
        console.print("Generating explanation...", style="dim")

        # Spawn subprocess to generate explanation asynchronously
        asyncio.create_task(self._generate_crumb_explanation(name))

    async def _generate_crumb_explanation(self, name: str) -> None:
        """Generate AI explanation for a crumb."""
        crumb = self.crumb_manager.get_crumb(name)
        if not crumb:
            return

        command = crumb.get("command", "")
        if not command:
            return

        try:
            explanation_prompt = f"Summarize this command in one line (10-15 words max): {command}"
            result = await self.assistant.send_prompt(prompt=explanation_prompt, command_mode=False)
            explanation = result.content.strip()

            if explanation:
                self.crumb_manager.update_explanation(name, explanation)
                from rich.text import Text

                # Strip ANSI codes from explanation
                clean_explanation = re.sub(r'\x1b\[([0-9;]*[mGK])', '', explanation)

                text = Text()
                text.append("Explanation added: ", style="cyan")
                text.append(clean_explanation)
                console.print(text)
        except Exception as e:
            console.print(f"Could not generate explanation: {e}", style="yellow")

    async def _add_crumb_manual(self, name: str, command: str) -> None:
        """Manually add a crumb with a command."""
        self.crumb_manager.save_crumb(
            name=name,
            prompt="Manual addition",
            response="",
            command=command,
        )

        console.print(f"Added crumb '{name}'!", style="green")
        console.print("Generating explanation...", style="dim")

        # Spawn subprocess to generate explanation asynchronously
        asyncio.create_task(self._generate_crumb_explanation(name))

    async def _delete_crumb(self, name: str) -> None:
        """Delete a crumb."""
        if self.crumb_manager.delete_crumb(name):
            console.print(f"Deleted crumb '{name}'.", style="green")
        else:
            console.print(f"Crumb '{name}' not found.", style="yellow")

    async def _use_crumb(self, name: str, args: list[str] | None = None) -> None:
        """Recall and execute a saved crumb.

        Args:
            name: Name of the crumb to execute
            args: Optional list of arguments to replace ${VAR} placeholders in the command
        """
        crumb = self.crumb_manager.get_crumb(name)
        if not crumb:
            console.print(f"Crumb '{name}' not found.", style="yellow")
            return

        explanation = crumb.get("explanation", "") or "No explanation"
        command = crumb.get("command", "") or "No command"

        # Substitute placeholders with provided arguments
        if args and command != "No command":
            command = substitute_placeholders(command, args)

        console.print(f"\n[bold cyan]Crumb: {name}[/bold cyan]")
        console.print(f"Explanation: {explanation}", style="green")
        console.print("Command: ", style="cyan", end="")
        console.print(command, highlight=False)

        if command and command != "No command":
            # Execute the command
            await self._run_shell_command(command)

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
    try:
        result = await rubber_ducky.send_prompt(prompt=prompt, code=code)
    except Exception as e:
        error_msg = str(e)
        if "unauthorized" in error_msg.lower() or "401" in error_msg:
            console.print("\n[red]Authentication Error (401)[/red]")
            console.print("You're trying to use a cloud model but don't have valid credentials.", style="yellow")

            # Check if API key is set
            api_key = os.environ.get("OLLAMA_API_KEY")
            if api_key:
                console.print("\nAn OLLAMA_API_KEY is set, but it appears invalid.", style="yellow")
            else:
                console.print("\n[bold]OLLAMA_API_KEY environment variable is not set.[/bold]", style="yellow")

            console.print("\nOptions:", style="bold")
            console.print("  1. Use --local flag to access local models:", style="dim")
            console.print("     ducky --local", style="cyan")
            console.print("  2. Select a local model with /local command", style="dim")
            console.print("  3. Set up Ollama cloud API credentials:", style="dim")
            console.print("     export OLLAMA_API_KEY='your-api-key-here'", style="cyan")
            console.print("\nGet your API key from: https://ollama.com/account/api-keys", style="dim")
            console.print()
            raise
        else:
            raise

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


async def ducky() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", "-v", action="version", version=f"%(prog)s {__version__}"
    )
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
        "--yolo",
        "-y",
        action="store_true",
        help=" Automatically run the suggested command without confirmation",
    )
    parser.add_argument(
        "single_prompt",
        nargs="*",
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
        # Point Ollama client to local host and use qwen3 as default model
        os.environ["OLLAMA_HOST"] = "http://localhost:11434"
        args.model = args.model or "qwen3"
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

    # Handle crumb invocation mode
    crumb_manager = CrumbManager()
    if args.single_prompt:
        first_arg = args.single_prompt[0]
        if crumb_manager.has_crumb(first_arg):
            # Extract crumb arguments (everything after the crumb name)
            crumb_args = args.single_prompt[1:]

            crumb = crumb_manager.get_crumb(first_arg)
            if crumb:
                explanation = crumb.get("explanation", "") or "No explanation"
                command = crumb.get("command", "") or "No command"

                # Substitute placeholders with provided arguments
                if crumb_args and command != "No command":
                    command = substitute_placeholders(command, crumb_args)

                console.print(f"\n[bold cyan]Crumb: {first_arg}[/bold cyan]")
                console.print(f"Explanation: {explanation}", style="green")
                console.print("Command: ", style="cyan", end="")
                console.print(command, highlight=False)

                if command and command != "No command":
                    # Execute the command
                    await run_shell_and_print(
                        rubber_ducky,
                        command,
                        logger=logger,
                        history=rubber_ducky.messages,
                    )
            return

    # Handle single prompt mode
    if args.single_prompt:
        prompt = " ".join(args.single_prompt)
        result = await run_single_prompt(
            rubber_ducky, prompt, code=code, logger=logger
        )
        if result.command:
            if args.yolo:
                await run_shell_and_print(
                    rubber_ducky,
                    result.command,
                    logger=logger,
                    history=rubber_ducky.messages,
                )
            elif copy_to_clipboard(result.command):
                console.print("\n[green]✓[/green] Command copied to clipboard")
        return

    await interactive_session(rubber_ducky, logger=logger, code=code)


def substitute_placeholders(command: str, args: list[str]) -> str:
    """Replace ${VAR} and $var placeholders in command with provided arguments.

    Args:
        command: The command string with placeholders
        args: List of arguments to substitute. The first unique variable name
              maps to args[0], the second unique name maps to args[1], etc.

    Returns:
        Command with placeholders replaced. Reused variable names get the
        same argument value. Falls back to env vars for unreplaced placeholders.
    """
    result = command
    placeholder_pattern = re.compile(r'\$\{([^}]+)\}|\$(\w+)')

    # First pass: collect unique variable names in order of appearance
    unique_vars = []
    seen_vars = set()
    for match in placeholder_pattern.finditer(command):
        var_name = match.group(1) or match.group(2)
        if var_name not in seen_vars:
            seen_vars.add(var_name)
            unique_vars.append(var_name)

    # Map unique variable names to arguments
    var_map = {}
    for i, var_name in enumerate(unique_vars):
        if i < len(args):
            var_map[var_name] = args[i]

    # Second pass: replace all placeholders using the map
    def replace_placeholder(match: re.Match) -> str:
        var_name = match.group(1) or match.group(2)
        if var_name in var_map:
            return var_map[var_name]
        # Fallback to environment variable
        return os.environ.get(var_name, match.group(0))

    result = placeholder_pattern.sub(replace_placeholder, result)
    return result


def main() -> None:
    asyncio.run(ducky())


if __name__ == "__main__":
    main()
