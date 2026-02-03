# Release 1.6.6

## Changes

### Added
- Automatic update checking on startup - notifies users once per day if a new version is available
- New `--upgrade` / `-u` flag to upgrade ducky via `uv tool upgrade`
- Background update check that runs non-blocking in interactive mode
- Update check caching in `~/.ducky/version_check_cache` (checks PyPI max once per day)

### Changed
- Update check is skipped in quiet mode, piped input, or single prompt mode for faster execution

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
