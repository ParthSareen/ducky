# Rubber Ducky

Rubber Ducky is an inline terminal companion that turns natural language prompts into runnable shell commands. Paste multi-line context, get a suggested command, and run it without leaving your terminal.

## Quick Start

| Action | Command |
| --- | --- |
| Install globally | `uv tool install rubber-ducky` |
| Run once | `uvx rubber-ducky -- --help` |
| Local install | `uv pip install rubber-ducky` |

Requirements:
- [Ollama](https://ollama.com) running locally
- Model available via Ollama (default: `qwen3-coder:480b-cloud`, install with `ollama pull qwen3-coder:480b-cloud`)

## Usage

```
ducky                 # interactive inline session
ducky --directory src  # preload code from a directory
ducky --model llama3   # use a different Ollama model
```

Both `ducky` and `rubber-ducky` executables map to the same CLI, so `uvx rubber-ducky -- <args>` works as well.

### Inline Session (default)

Launching `ducky` with no arguments opens the inline interface:
- **Enter** submits; **Ctrl+J** inserts a newline (helpful when crafting multi-line prompts). Hitting **Enter on an empty prompt** reruns the latest suggested command; if none exists yet, it explains the most recent shell output.
- **Ctrl+R** re-runs the last suggested command.
- Prefix any line with **`!`** (e.g., `!ls -la`) to run a shell command immediately.
- Arrow keys browse prompt history, backed by `~/.ducky/prompt_history`.
- Every prompt, assistant response, and executed command is logged to `~/.ducky/conversation.log`.
- Press **Ctrl+D** on an empty line to exit.
- Non-interactive runs such as `cat prompt.txt | ducky` print one response (and suggested command) before exiting; if a TTY is available you'll be asked whether to run the suggested command immediately.
- If `prompt_toolkit` is unavailable in your environment, Rubber Ducky falls back to a basic input loop (no history or shortcuts); install `prompt-toolkit>=3.0.48` to unlock the richer UI.

`ducky --directory <path>` streams the contents of the provided directory to the assistant the next time you submit a prompt (the directory is read once at startup).

## Development (uv)

```
uv sync
uv run ducky --help
```

`uv sync` creates a virtual environment and installs dependencies defined in `pyproject.toml` / `uv.lock`.

## Telemetry & Storage

Rubber Ducky stores:
- `~/.ducky/prompt_history`: readline-compatible history file.
- `~/.ducky/conversation.log`: JSON lines with timestamps for prompts, assistant messages, and shell executions.

No other telemetry is collected; delete the directory if you want a fresh slate.
