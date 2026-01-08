# Rubber Ducky

Turn natural language into bash commands without leaving your terminal.

Rubber Ducky is an inline terminal companion that transforms your prompts into runnable shell commands. Paste multi-line context, get smart suggestions, and execute commands instantly.

---

## Quick Start

```bash
# Install globally (recommended)
uv tool install rubber-ducky

# Run interactively
ducky

# Quick one-shot
ducky "list all files larger than 10MB in current directory"

# From CLI with options
ducky --model qwen3
ducky --directory src
ducky --local

# Or use uvx (requires -- separator)
uvx rubber-ducky -- --model qwen3
```

Both `ducky` and `rubber-ducky` executables work identically.

### Requirements

- [Ollama](https://ollama.com) (running locally or using cloud models)
- Python 3.10+

---

## Features

- **Natural to Shell** - Describe what you want, get the bash command
- **Model Flexibility** - Switch between local Ollama models and cloud models
- **Crumbs** - Save and reuse commands with argument substitution
- **Piped Input** - Pipe output from other commands directly to ducky
- **Interactive REPL** - Rich terminal experience with history and shortcuts
- **Code Context** - Preload project code for AI awareness
- **Clipboard Support** - Copy commands across macOS, Windows, and Linux

---

## Key Concepts

### REPL (Interactive Mode)

Launch `ducky` to start an inline session:

```
ducky
```

**Key controls:**
- `Enter` - Submit prompt
- `Ctrl+J` - Insert newline (for multi-line prompts)
- `Empty Enter` - Rerun last command or explain shell output
- `Ctrl+R` - Re-run last suggested command
- `Ctrl+S` - Copy last command to clipboard
- `!<cmd>` - Run shell command immediately
- `Arrow keys` - Browse history
- `Ctrl+D` - Exit

### Models

Rubber Ducky supports both local and cloud models:

- `/model` - Interactive model selection
- `/local` - List local models (localhost:11434)
- `/cloud` - List cloud models (ollama.com)
- Last used model is saved automatically

**Startup flags:**
- `--local` / `-l` - Use local Ollama with qwen3 default
- `--model <name>` / `-m` - Specify model directly

### Crumbs

Crumbs are saved command shortcuts. Store frequently-used commands or complex workflows:

```
>> How do I list all running Python processes?
...
Suggested: ps aux | grep python | grep -v grep
>> /crumb pyprocs
Saved crumb 'pyprocs'!
```

**Invoke crumb:**
```
>> pyprocs
Crumb: pyprocs
Command: ps aux | grep python | grep -v grep
...
```

**With argument substitution:**
```bash
# Crumb command: git worktree add "../$var-$other" -b $var3
ducky at feature backend develop
# Executes: git worktree add "../feature-backend" -b develop
```

---

## Usage Guide

### Interactive Mode

Default mode. Perfect for development sessions.

```bash
ducky
```

Load code context for better suggestions:

```bash
ducky --directory src
```

### Single-Shot Mode

Get one command suggestion and exit.

```bash
ducky "find all TODO comments in src/"
```

Copy to clipboard automatically:

```bash
ducky "build and run tests"
```

### Piped Input

Process text from other commands:

```bash
cat error.log | ducky "what's wrong here?"
git diff | ducky "summarize these changes"
```

### Run Without Confirmation

Auto-execute suggested commands:

```bash
ducky --yolo "restart the nginx service"
```

---

## Crumbs Quick Reference

| Command | Description |
|---------|-------------|
| `/crumbs` | List all saved crumbs |
| `/crumb <name>` | Save last command as crumb |
| `/crumb add <name> <cmd>` | Manually add crumb |
| `/crumb del <name>` | Delete crumb |
| `<name>` | Execute crumb |
| `/crumb help` | Detailed crumb help |

**Argument Substitution:**

Crumbs support `${VAR}` and `$var` placeholder styles:

```bash
# Create crumb with placeholders
git worktree add "../$var-$other" -b $var3

# Invoke with arguments
ducky at feature backend develop
```

Both styles are interchangeable.

---

## Command Reference

### Inline Commands

| Command | Action |
|---------|--------|
| `/help` | Show all commands |
| `/clear` / `/reset` | Clear conversation history |
| `/model` | Select model (interactive) |
| `/local` | List local models |
| `/cloud` | List cloud models |
| `/run` / `:run` | Re-run last command |
| `/expand` | Show full output of last shell command |

### CLI Flags

| Flag | Description |
|------|-------------|
| `--directory <path>` / `-d` | Preload code from directory |
| `--model <name>` / `-m` | Specify Ollama model |
| `--local` / `-l` | Use local Ollama (qwen3 default) |
| `--yolo` / `-y` | Auto-run without confirmation |
| `<prompt>` | Single prompt mode (copied to clipboard) |

---

## Tips & Tricks

### Efficient Workflows

```bash
# Preload project context
ducky --directory src

# Reuse complex commands with crumbs
docker ps | ducky "kill all containers"
>> /crumb killall

# Chain commands
!ls -la
ducksy "find large files"

# Use history
[↑] Recall previous prompts
[↓] Navigate command history
```

### Keyboard Shortcuts Reference

| Key | Action |
|-----|--------|
| `Enter` | Submit prompt |
| `Ctrl+J` | Insert newline |
| `Empty Enter` | Rerun last command or explain |
| `Ctrl+R` | Re-run last suggested command |
| `Ctrl+S` | Copy to clipboard |
| `Ctrl+D` | Exit |
| `!cmd` | Run shell command directly |

### Crumb Patterns

```bash
# Save after complex command
>> docker-compose up -d && wait && docker-compose logs
>> /crumb start-logs

# Manually add with arguments
>> /crumb add deploy-prod docker build -t app:latest && docker push app:latest

# Use for common workflows
>> ls -la
find . -type f -name "*.py" | xargs wc -l
>> /crumb count-py
```

---

## Storage

Rubber Ducky stores data in `~/.ducky/`:

| File | Purpose |
|------|---------|
| `prompt_history` | readline-compatible history |
| `conversation.log` | JSON log of all interactions |
| `config` | User preferences (last model) |
| `crumbs.json` | Saved crumb shortcuts |

Delete the entire directory for a fresh start.

---

## Development

```bash
# Clone and setup
git clone <repo>
cd ducky
uv sync

# Run
uv run ducky --help
uv run ducky

# Lint
uv run ruff check .
```

---

## License

MIT © 2023 Parth Sareen
