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
ducky                      # interactive inline session
ducky --directory src      # preload code from a directory
ducky --model qwen3        # use a different Ollama model
ducky --local              # use local models with gemma2:9b default
ducky --poll log-crumb     # start polling mode for a crumb
```

Both `ducky` and `rubber-ducky` executables map to the same CLI, so `uvx rubber-ducky -- <args>` works as well.

### Inline Session (default)

Launching `ducky` with no arguments opens the inline interface:
- **Enter** submits; **Ctrl+J** inserts a newline (helpful when crafting multi-line prompts). Hitting **Enter on an empty prompt** reruns the latest suggested command; if none exists yet, it explains the most recent shell output.
- **Ctrl+R** re-runs the last suggested command.
- **Ctrl+S** copies the last suggested command to clipboard.
- Prefix any line with **`!`** (e.g., `!ls -la`) to run a shell command immediately.
- Arrow keys browse prompt history, backed by `~/.ducky/prompt_history`.
- Every prompt, assistant response, and executed command is logged to `~/.ducky/conversation.log`.
- Press **Ctrl+D** on an empty line to exit.
- Non-interactive runs such as `cat prompt.txt | ducky` print one response (and suggested command) before exiting; if a TTY is available you'll be asked whether to run the suggested command immediately.
- If `prompt_toolkit` is unavailable in your environment, Rubber Ducky falls back to a basic input loop (no history or shortcuts); install `prompt-toolkit>=3.0.48` to unlock the richer UI.

`ducky --directory <path>` streams the contents of the provided directory to the assistant the next time you submit a prompt (the directory is read once at startup).

### Model Management

Rubber Ducky now supports easy switching between local and cloud models:
- **`/model`** - Interactive model selection between local and cloud models
- **`/local`** - List and select from local models (localhost:11434)
- **`/cloud`** - List and select from cloud models (ollama.com)
- Last used model is automatically saved and loaded on startup
- Type **`esc`** during model selection to cancel

### Additional Commands

- **`/help`** - Show all available commands and shortcuts
- **`/crumbs`** - List all available crumbs (default and user-created)
- **`/clear`** or **`/reset`** - Clear conversation history
- **`/poll <crumb>`** - Start polling session for a crumb
- **`/poll <crumb> -i <interval>`** - Start polling with custom interval
- **`/poll <crumb> -p <prompt>`** - Start polling with custom prompt
- **`/stop-poll`** - Stop current polling session
- **`/run`** or **`:run`** - Re-run the last suggested command

## Crumbs

Crumbs are simple scripts that can be executed within Rubber Ducky. They are stored in `~/.ducky/crumbs/` (for user crumbs) and shipped with the package (default crumbs).

Rubber Ducky ships with the following default crumbs:

| Crumb | Description |
|-------|-------------|
| `git-status` | Show current git status and provide suggestions |
| `git-log` | Show recent commit history with detailed information |
| `recent-files` | Show recently modified files in current directory |
| `disk-usage` | Show disk usage with highlights |
| `system-health` | Show CPU, memory, and system load metrics |
| `process-list` | Show running processes with analysis |

**Tip:** Run `/crumbs` in interactive mode to see all available crumbs with descriptions and polling status.

To use a crumb, simply mention it in your prompt:
```
Can you use the git-status crumb to see what needs to be committed?
```

**Note:** User-defined crumbs (in `~/.ducky/crumbs/`) override default crumbs with the same name.

### Creating Crumbs

To create a new crumb:

1. Create a new directory in `~/.ducky/crumbs/` with your crumb name
2. Add an `info.txt` file with metadata:
   ```
   name: your-crumb-name
   type: shell
   description: Brief description of what this crumb does
   ```
3. Add your executable script file (e.g., `your-crumb-name.sh`)
4. Create a symbolic link in `~/.local/bin` to make it available as a command:
   ```bash
   ln -s ~/.ducky/crumbs/your-crumb-name/your-crumb-name.sh ~/.local/bin/your-crumb-name
   ```

### Polling Mode

Crumbs can be configured for background polling, where the crumb script runs at intervals and the AI analyzes the output.

**Enabling Polling in a Crumb:**

Add polling configuration to your crumb's `info.txt`:
```
name: log-crumb
type: shell
description: Fetch and analyze server logs
poll: true
poll_type: interval          # "interval" (run repeatedly) or "continuous" (run once, tail output)
poll_interval: 5             # seconds between polls
poll_prompt: Analyze these logs for errors, warnings, or anomalies. Be concise.
```

**Polling via CLI:**

```bash
# Start polling with crumb's default configuration
ducky --poll log-crumb

# Override interval
ducky --poll log-crumb --interval 10

# Override prompt
ducky --poll log-crumb --prompt "Extract only error messages"
```

**Polling via Interactive Mode:**

```bash
ducky
>> /poll log-crumb                    # Use crumb defaults
>> /poll log-crumb -i 10              # Override interval
>> /poll log-crumb -p "Summarize"     # Override prompt
>> /stop-poll                         # Stop polling
```

**Example Crumb with Polling:**

Directory: `~/.ducky/crumbs/server-logs/`

```
info.txt:
  name: server-logs
  type: shell
  description: Fetch and analyze server logs
  poll: true
  poll_type: interval
  poll_interval: 5
  poll_prompt: Analyze these logs for errors, warnings, or anomalies. Be concise.

server-logs.sh:
  #!/bin/bash
  curl -s http://localhost:8080/logs | tail -50
```

**Polling Types:**

- **interval**: Run the crumb script at regular intervals (default)
- **continuous**: Run the crumb once in the background and stream its output, analyzing periodically

**Stopping Polling:**

Press `Ctrl+C` at any time to stop polling. In interactive mode, you can also use `/stop-poll`.

## Documentation

- **Polling Feature Guide**: See [examples/POLLING_USER_GUIDE.md](examples/POLLING_USER_GUIDE.md) for detailed instructions on creating and using polling crumbs
- **Mock Log Crumb**: See [examples/mock-logs/](examples/mock-logs/) for an example polling crumb

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
- `~/.ducky/config`: User preferences including last selected model.

No other telemetry is collected; delete the directory if you want a fresh slate.
