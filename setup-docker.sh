#!/bin/bash
# Quick setup script for Docker deployment

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}HB MQTT Signal Bot - Docker Setup${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Error: Docker is not installed${NC}"
    echo "Please install Docker from https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null && ! docker-compose --version &> /dev/null; then
    echo -e "${YELLOW}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose from https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker is installed"
echo ""

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.docker.example .env
    echo "✓ Created .env file"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Please edit .env with your configuration:${NC}"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - TELEGRAM_CHAT_ID"
    echo "  - HUMMINGBOT_API_PASSWORD"
    echo "  - Other settings as needed"
    echo ""
    read -p "Press Enter after you've configured .env (or Ctrl+C to exit and configure later)..."
else
    echo "✓ .env file already exists"
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p logs data mosquitto/data mosquitto/log
echo "✓ Directories created"

# Make docker.sh executable
chmod +x docker.sh
echo "✓ Made docker.sh executable"

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Review your .env configuration"
echo "  2. Start the bot: ./docker.sh start"
echo "  3. View logs: ./docker.sh logs"
echo ""
echo "For more commands, run: ./docker.sh"
echo ""
