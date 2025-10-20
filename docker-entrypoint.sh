#!/bin/bash

# MQTT to Telegram Rankings Bot - Docker Entrypoint Script
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Function to validate required environment variables
validate_env() {
    local required_vars=(
        "TELEGRAM_BOT_TOKEN"
        "TELEGRAM_CHAT_ID" 
        "MQTT_BROKER_HOST"
        "HUMMINGBOT_API_URL"
        "HUMMINGBOT_API_PASSWORD"
    )
    
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -ne 0 ]]; then
        error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            error "  - $var"
        done
        error "Please set all required environment variables before starting."
        exit 1
    fi
    
    log "Environment validation passed ✓"
}

# Function to handle graceful shutdown
graceful_shutdown() {
    log "Received shutdown signal, initiating graceful shutdown..."
    
    if [[ -n "$MAIN_PID" ]]; then
        log "Sending SIGTERM to main process (PID: $MAIN_PID)"
        kill -TERM "$MAIN_PID" 2>/dev/null || true
        
        # Wait for graceful shutdown
        for i in {1..30}; do
            if ! kill -0 "$MAIN_PID" 2>/dev/null; then
                log "Main process shutdown gracefully ✓"
                break
            fi
            if [[ $i -eq 30 ]]; then
                warn "Force killing main process after 30 seconds"
                kill -KILL "$MAIN_PID" 2>/dev/null || true
            else
                sleep 1
            fi
        done
    fi
    
    log "Shutdown completed"
    exit 0
}

# Set up signal handlers
trap graceful_shutdown SIGTERM SIGINT

# Main execution
main() {
    log "Starting MQTT to Telegram Rankings Bot"
    log "Container User: $(whoami)"
    log "Working Directory: $(pwd)"
    log "Python Version: $(python --version)"
    
    # Validate environment
    validate_env
    
    # Create directories
    mkdir -p /app/logs /app/data /app/conf
    
    # Start the application
    log "Starting main application..."
    
    if [[ $# -eq 0 ]]; then
        python main_execution_bot.py &
        MAIN_PID=$!
    else
        log "Executing custom command: $*"
        exec "$@" &
        MAIN_PID=$!
    fi
    
    log "Main process started with PID: $MAIN_PID"
    
    # Wait for the main process
    wait "$MAIN_PID"
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        log "Application exited normally"
    else
        error "Application exited with code: $exit_code"
    fi
    
    exit $exit_code
}

# Only run main if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi