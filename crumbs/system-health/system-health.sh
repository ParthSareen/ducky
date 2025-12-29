#!/usr/bin/env bash

# Show system health metrics
# Works on macOS and Linux

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)

echo "=== System Health ==="
echo "Platform: $OS"
echo "Uptime: $(uptime)" | awk '{print $3, $4}'
echo "Users logged in: $(who | wc -l | tr -d ' ')"

echo -e "\n=== CPU Usage ==="

if [ "$OS" == "macos" ]; then
    echo "Load averages (1m, 5m, 15m): $(sysctl -n vm.loadavg)"
    top -l 1 | grep "CPU usage"
elif [ "$OS" == "linux" ]; then
    echo "Load averages (1m, 5m, 15m): $(uptime | awk -F'load average:' '{print $2}')"
    top -bn1 | grep "Cpu(s)"
fi

echo -e "\n=== Memory Usage ==="

if [ "$OS" == "macos" ]; then
    # macOS memory
    echo "Memory Stats:"
    vm_stat | perl -ne '/page size of (\d+)/ and $ps=$1; /Pages\s+([^:]+)[^\d]+(\d+)/ and printf("%-16s % 16.2f MB\n", "$1:", $2 * $ps / 1048576);'
elif [ "$OS" == "linux" ]; then
    free -h
fi

echo -e "\n=== Disk Space ==="
df -h | grep -vE '^Filesystem|tmpfs|cdrom|devtmpfs'

echo -e "\n=== Network Connections ==="

if [ "$OS" == "macos" ]; then
    netstat -an | grep ESTABLISHED | wc -l | xargs echo "Active network connections:"
elif [ "$OS" == "linux" ]; then
    ss -tun | grep ESTAB | wc -l | xargs echo "Active network connections:"
fi

echo -e "\n=== Top 5 Processes by CPU ==="
ps aux | sort -rk 3,3 | head -11 | tail -10 | awk '{printf "%-10s %6s %s\n", $1, $3, $11}'

echo -e "\n=== Top 5 Processes by Memory ==="
ps aux | sort -rk 4,4 | head -11 | tail -10 | awk '{printf "%-10s %6s %s\n", $1, $4, $11}'
