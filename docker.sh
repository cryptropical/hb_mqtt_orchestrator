#!/bin/bash
# Docker management script for HB MQTT Signal Telegram Bot

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Helper functions
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env exists
check_env() {
    if [ ! -f .env ]; then
        warning ".env file not found!"
        echo "Creating .env from .env.docker.example..."
        cp .env.docker.example .env
        warning "Please edit .env with your configuration before starting the bot"
        exit 1
    fi
}

# Function to display usage
usage() {
    cat << EOF
Usage: ./docker.sh [COMMAND]

Commands:
    start           Start the bot in detached mode
    stop            Stop the bot
    restart         Restart the bot
    logs            View bot logs (follow mode)
    logs-mqtt       View MQTT broker logs
    status          Show status of containers
    build           Build/rebuild Docker images
    clean           Stop and remove containers and volumes
    shell           Open a shell in the bot container
    test            Run bot in test mode with auto-unwind
    update          Pull latest code, rebuild, and restart

Examples:
    ./docker.sh start
    ./docker.sh logs
    ./docker.sh test

EOF
    exit 1
}

# Main command handling
case "${1:-}" in
    start)
        check_env
        info "Starting MQTT Signal Telegram Bot..."
        docker-compose up -d
        info "Bot started! Use './docker.sh logs' to view logs"
        ;;
    
    stop)
        info "Stopping bot..."
        docker-compose down
        info "Bot stopped"
        ;;
    
    restart)
        info "Restarting bot..."
        docker-compose restart
        info "Bot restarted"
        ;;
    
    logs)
        info "Showing bot logs (Ctrl+C to exit)..."
        if [ -f "./view_logs.sh" ]; then
            ./view_logs.sh tail
        else
            docker-compose logs -f mqtt-telegram-bot
        fi
        ;;
    
    logs-mqtt)
        info "Showing MQTT broker logs (Ctrl+C to exit)..."
        docker-compose logs -f mqtt-broker
        ;;
    
    status)
        info "Container status:"
        docker-compose ps
        echo ""
        info "Resource usage:"
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
            hb_mqtt_signal_bot mqtt-broker 2>/dev/null || \
            warning "Containers not running"
        ;;
    
    build)
        info "Building Docker images..."
        docker-compose build --no-cache
        info "Build complete"
        ;;
    
    clean)
        warning "This will stop containers and remove volumes!"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            info "Cleaning up..."
            docker-compose down -v
            info "Cleanup complete"
        else
            info "Cancelled"
        fi
        ;;
    
    shell)
        info "Opening shell in bot container..."
        docker-compose exec mqtt-telegram-bot /bin/bash
        ;;
    
    test)
        check_env
        WAIT_TIME=${2:-180}
        info "Running test mode with ${WAIT_TIME}s wait time..."
        docker-compose run --rm mqtt-telegram-bot \
            python main_execution_bot.py --test-unwind --wait=$WAIT_TIME
        ;;
    
    update)
        info "Updating bot..."
        git pull
        docker-compose down
        docker-compose build
        docker-compose up -d
        info "Update complete! Bot is running"
        ;;
    
    *)
        usage
        ;;
esac
