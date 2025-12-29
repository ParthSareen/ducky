#!/usr/bin/env bash

# Show recent commit history with details

if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Not a git repository."
    exit 1
fi

# Default to showing last 10 commits
COMMIT_COUNT=10

if [ -n "$1" ] && [[ "$1" =~ ^[0-9]+$ ]]; then
    COMMIT_COUNT=$1
fi

echo "=== Recent ${COMMIT_COUNT} Commits ==="
git log --oneline -$COMMIT_COUNT

echo -e "\n=== Detailed View of Last ${COMMIT_COUNT} Commits ==="
git log -${COMMIT_COUNT} --pretty=format:"%h - %an, %ar : %s" --stat

echo -e "\n=== Author Statistics ==="
git shortlog -sn --all -${COMMIT_COUNT} 2>/dev/null
