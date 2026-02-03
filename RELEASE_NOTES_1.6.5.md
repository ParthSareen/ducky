# Release 1.6.5

## Changes

### Fixed
- Fixed greyed-out text in responses - output now displays in normal color
- Commands wrapped in backticks are now properly stripped
- Piped input with user prompts now handled correctly (disables command mode for explanations)

### Changed
- New `<command></command>` template format for structured command extraction
- Command tags are now hidden from display output while still being extracted for execution
- Improved command parsing with better multiline support

## Installation

```bash
# Via uv (recommended)
uv tool install rubber-ducky

# Via pip
pip install rubber-ducky

# Upgrade
uv tool upgrade rubber-ducky
pip install --upgrade rubber-ducky
```
