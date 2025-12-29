#!/usr/bin/env bash

# Generate mock log data for testing polling

# Random timestamps
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Array of log levels and messages
LEVELS=("INFO" "WARNING" "ERROR" "DEBUG")
MESSAGES=(
    "User login successful: user_id=USER_123"
    "Database query completed in 45ms"
    "API request from IP_ADDRESS"
    "Cache hit for key: user_settings_KEY"
    "Connection timeout to external service"
    "Disk usage at 85%"
    "Payment processed: order_id=ORDER_789"
    "Scheduled task 'daily_backup' started"
    "Failed to send email notification"
    "New user registration: email=user@example.local"
    "Memory usage: 2.4GB / 8GB"
    "Request rate: 150 req/s"
)

# Select random level and message
LEVEL=${LEVELS[$RANDOM % ${#LEVELS[@]}]}
MESSAGE=${MESSAGES[$RANDOM % ${#MESSAGES[@]}]}

# Add some variety - occasionally include errors
if [ $RANDOM -lt 4 ]; then
    LEVEL="ERROR"
    MESSAGE="Failed to process request: timeout"
elif [ $RANDOM -lt 4 ]; then
    LEVEL="WARNING"
    MESSAGE="High latency detected: response time > 500ms"
fi

# Format the log entry
echo "[$TIMESTAMP] $LEVEL - $MESSAGE"
