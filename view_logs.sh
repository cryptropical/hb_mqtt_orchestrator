#!/bin/bash
# Log viewing convenience script for MQTT Telegram Execution Bot

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

LOG_FILE="logs/mqtt_telegram_execution_bot.log"

info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to display usage
usage() {
    cat << EOF
Usage: ./view_logs.sh [COMMAND] [OPTIONS]

Commands:
    tail            View live logs (tail -f)
    view [N]        View last N lines (default: 50)
    search TERM     Search for specific term in logs
    errors          Show only error messages
    today           Show only today's logs
    size            Show log file size and info
    rotate          Force log rotation (if needed)

Examples:
    ./view_logs.sh tail
    ./view_logs.sh view 100
    ./view_logs.sh search "MQTT"
    ./view_logs.sh errors

EOF
    exit 1
}

# Check if log file exists
check_log_file() {
    if [ ! -f "$LOG_FILE" ]; then
        error "Log file not found: $LOG_FILE"
        echo "Make sure the bot has been running to generate logs."
        exit 1
    fi
}

case "${1:-}" in
    tail)
        check_log_file
        info "Following live logs (Ctrl+C to exit)..."
        tail -f "$LOG_FILE"
        ;;
    
    view)
        check_log_file
        LINES=${2:-50}
        info "Showing last $LINES lines:"
        tail -n "$LINES" "$LOG_FILE"
        ;;
    
    search)
        check_log_file
        if [ -z "${2:-}" ]; then
            error "Search term required"
            echo "Usage: ./view_logs.sh search SEARCH_TERM"
            exit 1
        fi
        info "Searching for '$2' in logs:"
        grep --color=always -i "$2" "$LOG_FILE" || echo "No matches found for '$2'"
        ;;
    
    errors)
        check_log_file
        info "Showing error messages:"
        grep --color=always -E "(ERROR|FATAL|Exception|Error)" "$LOG_FILE" || echo "No errors found"
        ;;
    
    today)
        check_log_file
        TODAY=$(date +%Y-%m-%d)
        info "Showing today's logs ($TODAY):"
        grep "$TODAY" "$LOG_FILE" || echo "No logs found for today"
        ;;
    
    size)
        check_log_file
        info "Log file information:"
        ls -lh "$LOG_FILE"
        echo ""
        info "Log file rotation files:"
        ls -lh logs/mqtt_telegram_execution_bot.log* 2>/dev/null || echo "No rotation files found"
        ;;
    
    rotate)
        info "Checking log rotation..."
        # This would typically be handled automatically by the RotatingFileHandler
        # but we can show the status
        if [ -f "$LOG_FILE" ]; then
            SIZE=$(wc -c < "$LOG_FILE")
            SIZE_MB=$((SIZE / 1024 / 1024))
            info "Current log file size: ${SIZE_MB}MB"
            if [ $SIZE_MB -gt 50 ]; then
                warning "Log file is larger than 50MB. Rotation should occur automatically."
            else
                info "Log file size is within limits."
            fi
        fi
        ;;
    
    *)
        usage
        ;;
esac
