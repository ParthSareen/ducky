#!/usr/bin/env bash

# Show recently modified files in current directory
# Takes optional argument for number of files to show (default 20)

FILE_COUNT=20

if [ -n "$1" ] && [[ "$1" =~ ^[0-9]+$ ]]; then
    FILE_COUNT=$1
fi

echo "=== ${FILE_COUNT} Most Recently Modified Files ==="
find . -type f -not -path '*/\.*' -not -path '*/node_modules/*' -not -path '*/\.git/*' -not -path '*/venv/*' -not -path '*/\__pycache__/*' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -${FILE_COUNT} | awk '{print strftime("%Y-%m-%d %H:%M:%S", $1), $2}'
