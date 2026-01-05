# Rubber Ducky

Rubber Ducky is an inline terminal companion that turns natural language prompts into runnable shell commands. Paste multi-line context, get a suggested command, and run it without leaving your terminal.

## Quick Start

| Action | Command |
| --- | --- |
| Install globally | `uv tool install rubber-ducky` |
| Run once | `uvx rubber-ducky -- --help` |
| Local install | `uv pip install rubber-ducky` |

Requirements:
- [Ollama](https://ollama.com) running locally or use cloud models
- Model available via Ollama (default: `glm-4.7:cloud`)

## Usage

```
ducky                      # interactive inline session
ducky --directory src      # preload code from a directory
ducky --model qwen3        # use a different Ollama model
ducky --local              # use local models with qwen3 default
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
- **`/crumbs`** - List all saved crumb shortcuts
- **`/crumb <name>`** - Save the last AI-suggested command as a named crumb
- **`/crumb add <name> <command>`** - Manually add a crumb with a specific command
- **`/crumb del <name>`** - Delete a saved crumb
- **`<crumb-name>`** - Invoke a saved crumb (displays info and executes the command)
- **`/clear`** or **`/reset`** - Clear conversation history
- **`/run`** or **`:run`** - Re-run the last suggested command

## Crumbs

Crumbs are saved command shortcuts that let you quickly reuse AI-generated bash commands without regenerating them each time. Perfect for frequently-used workflows or complex commands.

### Saving Crumbs

When the AI suggests a command that you want to reuse:

1. Get a command suggestion from ducky
2. Save it immediately: `/crumb <name>`
3. Example:
   ```
   >> How do I list all Ollama processes?
   ...
   Suggested command: ps aux | grep -i ollama | grep -v grep
   >> /crumb ols
   Saved crumb 'ols'!
   Generating explanation...
   Explanation added: Finds and lists all running Ollama processes.
   ```

The crumb is saved with:
- The original command
- An AI-generated one-line explanation
- A timestamp

### Invoking Crumbs

Simply type the crumb name in the REPL or use it as a CLI argument:

**In REPL:**
```
>> ols

Crumb: ols
Explanation: Finds and lists all running Ollama processes.
Command: ps aux | grep -i ollama | grep -v grep

$ ps aux | grep -i ollama | grep -v grep
user123  12345  0.3  1.2  456789  98765 ?  Sl  10:00   0:05 ollama serve
```

**From CLI:**
```bash
ducky ols              # Runs the saved crumb and displays output
```

When you invoke a crumb:
1. It displays the crumb name, explanation, and command
2. Automatically executes the command
3. Shows the output

### Managing Crumbs

**List all crumbs:**
```bash
>> /crumbs
```

Output:
```
Saved Crumbs
=============
ols      | Finds and lists all running Ollama processes. | ps aux | grep -i ollama | grep -v grep
test     | Run tests and build project                  | pytest && python build.py
deploy   | Deploy to production                         | docker push app:latest
```

**Manually add a crumb:**
```bash
>> /crumb add deploy-prod docker build -t app:latest && docker push app:latest
```

**Delete a crumb:**
```bash
>> /crumb ols
Deleted crumb 'ols'.
```

### Storage

Crumbs are stored in `~/.ducky/crumbs.json` as JSON. Each crumb includes:
- `prompt`: Original user prompt
- `response`: AI's full response
- `command`: The suggested bash command
- `explanation`: AI-generated one-line summary
- `created_at`: ISO timestamp

**Example:**
```json
{
  "ols": {
    "prompt": "How do I list all Ollama processes?",
    "response": "To list all running Ollama processes...",
    "command": "ps aux | grep -i ollama | grep -v grep",
    "explanation": "Finds and lists all running Ollama processes.",
    "created_at": "2024-01-05T10:30:00.000000+00:00"
  }
}
```

Delete `~/.ducky/crumbs.json` to clear all saved crumbs.

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
