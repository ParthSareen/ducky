#!/usr/bin/env bash

# Show disk usage with highlights

echo "=== Disk Usage Overview ==="
df -h 2>/dev/null | grep -E "(/|Filesystem)"

echo -e "\n=== Detailed Disk Usage ==="
du -h -d 2 . 2>/dev/null | sort -hr | head -20

echo -e "\n=== Largest Files in Current Directory ==="
find . -type f -not -path '*/\.git/*' -not -path '*/node_modules/*' -not -path '*/venv/*' -not -path '*/\__pycache__/*' -exec du -h {} + 2>/dev/null | sort -rh | head -10
