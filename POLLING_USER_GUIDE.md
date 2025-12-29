# Polling Feature User Guide

This guide explains how to use the AI-driven background polling feature in Rubber Ducky.

## Overview

The polling feature allows you to run a crumb script at regular intervals and have AI analyze the output automatically. This is useful for:
- Monitoring server logs for errors or anomalies
- Tracking system metrics over time
- Watching for specific patterns in data streams
- Getting AI-powered insights on repeating data sources

---

## Quick Start Example

```bash
# Start polling with a pre-configured crumb
ducky --poll mock-logs
```

Output:
```
Starting interval polling for 'mock-logs' (interval: 5s)...
Poll prompt: Analyze these mock logs and identify any errors, warnings, or 
interesting patterns. Keep it brief.
Press Ctrl+C to stop polling.

[2025-12-28 23:02:43] Polling mock-logs...
Script output: 54 bytes
AI: Brief analysis of the mock log entry:
... (AI analysis) ...
```

---

## Creating a Polling Crumb

### Step 1: Create the Crumb Directory

```bash
mkdir -p ~/.ducky/crumbs/my-logs
```

### Step 2: Create the Configuration File

Create `~/.ducky/crumbs/my-logs/info.txt`:

```
name: my-logs
type: shell
description: Fetch and analyze application logs
poll: true
poll_type: interval          # Can be "interval" or "continuous"
poll_interval: 10            # Poll every 10 seconds
poll_prompt: Analyze these logs for errors, warnings, or unusual patterns. Be concise.
```

### Step 3: Create the Script

Create `~/.ducky/crumbs/my-logs/my-logs.sh`:

```bash
#!/usr/bin/env bash
# Fetch last 50 lines of application logs
tail -50 /var/log/app.log
```

### Step 4: Make the Script Executable

```bash
chmod +x ~/.ducky/crumbs/my-logs/my-logs.sh
```

### Step 5: Test the Crumb

```bash
# Test the script directly
~/.ducky/crumbs/my-logs/my-logs.sh

# Test with ducky polling
ducky --poll my-logs
```

---

## Configuration Reference

### info.txt Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Crumb name used to reference it |
| `type` | string | Yes | `shell` | Crumb type (currently only `shell` supported) |
| `description` | string | No | - | Human-readable description |
| `poll` | boolean | No | `false` | Enable polling for this crumb |
| `poll_type` | string | No | `interval` | Either `"interval"` (run repeatedly) or `"continuous"` (run once, stream) |
| `poll_interval` | integer | No | `2` | Seconds between polls (for `interval` type) |
| `poll_prompt` | string | No | `"Analyze this output."` | The prompt sent to AI with each poll's output |

### Poll Types

#### Interval Polling (default)
The script runs from scratch at each interval:
- ✅ Good for: Fetching logs, checking system resources, running commands
- ✅ Clean state: Each run starts fresh
- ⚠️ Higher resource usage if script is expensive

```
poll_type: interval
poll_interval: 10
```

Example:
```bash
#!/bin/bash
# Runs completely every 10 seconds
tail -50 /var/log/nginx/access.log
```

#### Continuous Polling
The script runs once in the background and output is streamed:
- ✅ Good for: Tail -f, real-time streams, long-running processes
- ✅ Lower resource: Process runs continuously without restarting
- ⚠️ Accumulated output grows over time

```
poll_type: continuous
poll_interval: 5
```

Example:
```bash
#!/bin/bash
# Runs once, continuously streams output
tail -f /var/log/app.log
```

---

## Using Polling

### Method 1: Command Line Interface

Start polling immediately without entering interactive mode:

```bash
# Use crumb's default settings
ducky --poll my-logs

# Override interval (every 10 seconds)
ducky --poll my-logs --interval 10

# Override prompt with custom instruction
ducky --poll my-logs --prompt "Extract only error messages and show counts"

# Combine overrides
ducky --poll my-logs --interval 15 --prompt "Summarize critical issues only"
```

### Method 2: Interactive Mode

Start ducky in interactive mode, then trigger polling:

```bash
ducky

# Start polling with defaults
>> /poll my-logs

# Override interval
>> /poll my-logs -i 10

# Override prompt
>> /poll my-logs -p "Count error types"

# Combine options
>> /poll my-logs -i 15 -p "Show only warnings and errors"

# Stop polling and return to interactive mode
>> /stop-poll
```

### Stopping Polling

From CLI:
- Press `Ctrl+C` at any time

From Interactive Mode:
- Press `Ctrl+C` at any time
- Or type `/stop-poll`

---

## Example Crumbs

### Example 1: Server Log Monitor

**Directory:** `~/.ducky/crumbs/server-logs/`

**info.txt:**
```
name: server-logs
type: shell
description: Monitor server logs for issues
poll: true
poll_type: interval
poll_interval: 5
poll_prompt: Analyze these logs for errors, warnings, or anomalies. Identify patterns if any.
```

**server-logs.sh:**
```bash
#!/bin/bash
curl -s http://localhost:8080/api/logs | tail -50
```

---

### Example 2: System Resource Monitor

**Directory:** `~/.ducky/crumbs/system-check/`

**info.txt:**
```
name: system-check
type: shell
description: Check system resources
poll: true
poll_type: interval
poll_interval: 30
poll_prompt: Analyze system health. Is anything concerning?
```

**system-check.sh:**
```bash
#!/bin/bash
echo "CPU Usage:"
top -l 1 | grep "CPU usage"
echo -e "\nMemory Usage:"
vm_stat | perl -ne '/page size of (\d+)/ and $ps=$1; /Pages\s+([^:]+)[^\d]+(\d+)/ and printf("%-16s % 16.2f Mi\n", "$1:", $2 * $ps / 1048576);'
echo -e "\nDisk Usage:"
df -h
```

---

### Example 3: Continuous Log Stream

**Directory:** `~/.ducky/crumbs/live-logs/`

**info.txt:**
```
name: live-logs
type: shell
description: Continuously monitor live logs
poll: true
poll_type: continuous
poll_interval: 3
poll_prompt: Summarize the latest log changes. Alert on critical issues.
```

**live-logs.sh:**
```bash
#!/bin/bash
tail -f /var/log/app.log
```

---

### Example 4: API Health Check

**Directory:** `~/.ducky/crumbs/api-health/`

**info.txt:**
```
name: api-health
type: shell
description: Check API endpoints
poll: true
poll_type: interval
poll_interval: 60
poll_prompt: Are there any failing endpoints or error spikes?
```

**api-health.sh:**
```bash
#!/bin/bash
echo "Main API:"
curl -s -w "\nHTTP Status: %{http_code}\nResponse Time: %{time_total}s\n" http://api.example.com/health -o /dev/null

echo -e "\nAuth Service:"
curl -s -w "\nHTTP Status: %{http_code}\nResponse Time: %{time_total}s\n" http://api.example.com/auth/health -o /dev/null
```

---

## Tips and Best Practices

### 1. Choose Appropriate Intervals
- **Fast-changing data:** 2-5 seconds (logs, metrics)
- **Medium-frequency changes:** 10-30 seconds (API checks, resource monitoring)
- **Slow-changing data:** 60+ seconds (long-running trends)

### 2. Write Efficient Scripts
- **For interval polling:** Scripts run from scratch each time
  - Limit output size (use `tail` instead of `cat`)
  - Avoid expensive operations (network calls, heavy computation)
  - Cache results if possible

- **For continuous polling:** Script runs once and streams
  - The process should be long-running (like `tail -f`)
  - Output should be finite (don't accumulate indefinitely)

### 3. Craft Effective Poll Prompts
Good prompts:
- ✅ "Analyze these logs for errors, warnings, or anomalies. Be concise."
- ✅ "Summarize the key findings and recommend next steps."
- ✅ "Identify any performance issues or resource constraints."

Avoid:
- ❌ Too generic: "Analyze this"
- ❌ Too complex: "Review every line, compare with historical data, generate reports, check for five different error types, and create a detailed analysis with recommendations..."

### 4. Test Locally First
```bash
# Verify your script works
~/.ducky/crumbs/my-logs/my-logs.sh

# Check output size
~/.ducky/crumbs/my-logs/my-logs.sh | wc -l

# Test with short interval
ducky --poll my-logs --interval 2
```

### 5. Manage Conversation History
Polling adds messages to the conversation history. For long-running sessions:
```bash
# Clear history periodically to keep AI context focused
ducky
>> /poll my-logs
# ... let it run ...
>> /stop-poll
>> /clear
>> /poll my-logs  # Continue with fresh context
```

---

## Troubleshooting

### Polling Not Starting

**Problem:** Command returns immediately without polling

**Possible causes:**
1. Crumb not found
   ```bash
   # Check available crumbs
   ducky --poll
   # See available crumbs listed
   ```

2. Script not executable
   ```bash
   chmod +x ~/.ducky/crumbs/my-logs/my-logs.sh
   ```

3. Ollama not running
   ```bash
   # Start Ollama
   ollama serve
   ```

### AI Returns Commands Instead of Analysis

**Problem:** AI responds with bash commands

**Status:** This should be fixed (added in version 1.3.0)

If you experience this:
```bash
# Check version
ducky --help  # Should show version 1.3.0+
```

### High Memory Usage

**Problem:** Memory grows over time during polling

**Solutions:**
1. Use continuous polling for data streams
2. Limit output size in your script
3. Clear conversation history periodically

### Script Takes Too Long

**Problem:** Polling interval shorter than script execution time

**Solutions:**
1. Increase `poll_interval` in info.txt
2. Optimize your script (limit data fetched)
3. Consider continuous polling instead

---

## Advanced Use Cases

### Multiple Concurrent Polls

Currently, only one polling session can run at a time. To monitor multiple sources:
1. Create a single crumb that aggregates multiple sources
2. Or run multiple ducky instances in separate terminals

```bash
# Terminal 1
ducky --poll logs

# Terminal 2  
ducky --poll metrics
```

### Combining with Standard Ducky

Use polling for monitoring, then switch to interactive mode for deeper analysis:

```bash
# Monitor for issues
ducky --poll my-logs

# Press Ctrl+C when you see an issue, then:
ducky --directory /var/log
>> Show me the error logs from the last hour
>> Analyze these errors and suggest fixes
```

### Custom Poll Prompts for Different Contexts

Override prompts based on what you're looking for:

```bash
# Focus on errors
ducky --poll my-logs -p "Show only ERROR level logs"

# Focus on performance
ducky --poll my-logs -p "Analyze performance metrics and bottlenecks"

# Get a summary
ducky --poll my-logs -p "Give me a 2-sentence summary"
```

---

## File Locations

- **Crumbs directory:** `~/.ducky/crumbs/`
- **Conversation log:** `~/.ducky/conversation.log`
- **Prompt history:** `~/.ducky/prompt_history`
- **Configuration:** `~/.ducky/config`

---

## Support and Resources

- Main README: [README.md](README.md)
- Test Output Examples: [POLLING_TEST_OUTPUTS.md](POLLING_TEST_OUTPUTS.md)
- GitHub Issues: For bugs and feature requests

Happy polling! 🦆
