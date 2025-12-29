#!/usr/bin/env bash

# Show comprehensive git status and recent activity

echo "=== Git Status ==="
git status --short 2>/dev/null || echo "Not a git repository."

echo -e "\n=== Current Branch ==="
git branch --show-current 2>/dev/null || echo "Not a git repository."

echo -e "\n=== Last 3 Commits ==="
git log --oneline -3 2>/dev/null || echo "No commits found."

echo -e "\n=== Staged Changes (if any) ==="
git diff --cached --stat 2>/dev/null

echo -e "\n=== Unstaged Changes (if any) ==="
git diff --stat 2>/dev/null

echo -e "\n=== Untracked Files (if any) ==="
git ls-files --others --exclude-standard 2>/dev/null | head -20
