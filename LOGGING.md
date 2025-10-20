# Logging Configuration

This document describes the logging setup for the MQTT to Telegram Rankings Bot.

## Overview

The bot now saves logs to the `logs/` directory which is mounted from the Docker container to your host machine. This ensures logs persist even when the container is stopped or restarted.

## Log File Location

**Host Machine**: `./logs/mqtt_telegram_execution_bot.log`  
**Inside Container**: `/app/logs/mqtt_telegram_execution_bot.log`

## Log Rotation

The logging system includes automatic rotation to manage disk space:

- **Max file size**: 50MB per log file
- **Backup files**: 5 old log files are kept
- **Total disk usage**: ~250MB maximum (50MB × 5 files)

When the main log file reaches 50MB, it will be automatically renamed to `mqtt_telegram_execution_bot.log.1`, and a new log file will be created.

## Log Format

```
YYYY-MM-DD HH:MM:SS,mmm - logger_name - LEVEL - message
```

Example:
```
2025-10-08 17:28:06,700 - __main__.MQTTRankingsExecutionBot - INFO - Starting MQTT to Telegram Rankings Execution Bot
```

## Viewing Logs

### Method 1: Using the Log Viewing Script

We provide a convenient script `view_logs.sh` for viewing logs:

```bash
# View live logs (tail -f)
./view_logs.sh tail

# View last 50 lines
./view_logs.sh view

# View last N lines
./view_logs.sh view 100

# Search for specific terms
./view_logs.sh search "MQTT"
./view_logs.sh search "ERROR"

# Show only error messages
./view_logs.sh errors

# Show today's logs only
./view_logs.sh today

# Check log file size and rotation status
./view_logs.sh size
```

### Method 2: Using Docker Compose

```bash
# View live container logs
docker-compose logs -f mqtt-telegram-bot

# View last 100 lines of container logs
docker-compose logs --tail 100 mqtt-telegram-bot
```

### Method 3: Direct File Access

```bash
# View live logs
tail -f logs/mqtt_telegram_execution_bot.log

# View last 50 lines
tail -n 50 logs/mqtt_telegram_execution_bot.log

# Search in logs
grep -i "error" logs/mqtt_telegram_execution_bot.log
```

### Method 4: Enhanced Docker Script

```bash
# View logs using the enhanced docker script
./docker.sh logs
```

## Log Levels

The bot logs at different levels:

- **INFO**: General operational messages
- **WARNING**: Non-critical issues that should be noted
- **ERROR**: Error conditions that need attention
- **DEBUG**: Detailed diagnostic information (not shown by default)

## Log Content

The logs contain information about:

- **Startup/Shutdown**: Bot initialization and cleanup
- **MQTT Connection**: Connection status, subscriptions, message processing
- **Trading Operations**: Position opening/closing, bot health checks
- **Telegram Notifications**: Message sending status
- **Error Handling**: Exception details and recovery attempts
- **Performance**: API response times and processing metrics

## Docker Volume Mounting

The `docker-compose.yml` file mounts the logs directory:

```yaml
volumes:
  - ./logs:/app/logs
```

This ensures that:
- Logs persist when containers are restarted
- You can access logs from the host machine
- Log rotation files are preserved
- Log analysis tools can access the files

## Troubleshooting

### No Log File Generated

If no log file appears in `logs/`:

1. Check if the container is running: `docker-compose ps`
2. Check container logs: `docker-compose logs mqtt-telegram-bot`
3. Verify volume mounting in docker-compose.yml
4. Check directory permissions: `ls -la logs/`

### Log File Permissions

If you see permission errors:

```bash
# Fix ownership (replace 1000:1000 with your user:group if needed)
sudo chown -R $(id -u):$(id -g) logs/
```

### Large Log Files

If log files grow too large despite rotation:

1. Check rotation settings in `main_execution_bot.py`:
   - `maxBytes=50*1024*1024` (50MB)
   - `backupCount=5` (5 files)

2. Manually clean old logs:
```bash
# Remove old rotation files
rm logs/mqtt_telegram_execution_bot.log.[2-9]*
```

### Missing Logs

If logs seem to be missing entries:

1. Check the log level configuration
2. Verify the application is actually running and processing data
3. Check if there are multiple log files due to rotation

## Log Analysis Examples

### Finding Errors
```bash
./view_logs.sh errors
# OR
grep -E "(ERROR|FATAL|Exception)" logs/mqtt_telegram_execution_bot.log
```

### Monitoring Trading Activity
```bash
./view_logs.sh search "position"
./view_logs.sh search "LONG\|SHORT"
```

### Checking MQTT Connectivity
```bash
./view_logs.sh search "MQTT\|Connected\|Disconnected"
```

### Performance Monitoring
```bash
./view_logs.sh search "HTTP Request"
./view_logs.sh search "processed.*update"
```

## Best Practices

1. **Regular Monitoring**: Check logs periodically for errors or warnings
2. **Log Retention**: The automatic rotation keeps 5 files, adjust if needed
3. **Disk Space**: Monitor the `logs/` directory size occasionally
4. **Error Response**: Set up alerting for ERROR level messages
5. **Performance**: Monitor HTTP request times and processing delays

## Integration with Monitoring

You can integrate the logs with monitoring tools:

- **Elasticsearch + Kibana**: For log aggregation and visualization
- **Grafana**: For metrics and alerting
- **Logrotate**: For additional log management (if needed)
- **Cron Jobs**: For automated log cleanup or archiving

Example logrotate configuration (optional):
```
/path/to/logs/mqtt_telegram_execution_bot.log* {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```
