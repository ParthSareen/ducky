# Release 1.6.3

## Changes

### Added
- `--quiet` / `-q` flag to suppress startup messages and help text
- Startup banner with version, model status, and crumb count
- Ollama connection health check
- Model validation for local Ollama instances

### Changed
- Color scheme updated to yellow/white/black theme across the entire application
- Model response color changed from yellow to dim (grey)
- Suggested command color changed from white to yellow
- Crumb names in `/crumbs` display now show in bold yellow

## Installation

```bash
uv tool install rubber-ducky
```

## Upgrade

```bash
uv tool upgrade rubber-ducky
# or
pip install --upgrade rubber-ducky
```