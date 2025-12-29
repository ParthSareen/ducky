#!/usr/bin/env bash

# Show running processes with useful information

echo "=== Running Processes (Top 20 by CPU) ==="
ps aux | sort -rk 3,3 | head -21 | awk '{printf "%-8s %-6s %-8s %s\n", $1, $2, $3, $11}' | column -t

echo -e "\n=== Running Processes (Top 20 by Memory) ==="
ps aux | sort -rk 4,4 | head -21 | awk '{printf "%-8s %-6s %-8s %s\n", $1, $2, $4, $11}' | column -t

echo -e "\n=== Process Counts by User ==="
ps aux | awk '{print $1}' | sort | uniq -c | sort -rn | head -10

echo -e "\n=== Check for Specific Processes ==="
for proc in "node" "python" "java" "docker" "npm" "uv"; do
    count=$(pgrep -c "$proc" 2>/dev/null || echo "0")
    if [ "$count" -gt 0 ]; then
        echo "$proc: $count process(es)"
    fi
done | sort
