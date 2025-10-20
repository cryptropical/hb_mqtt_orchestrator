# Docker Deployment Guide

This guide explains how to run the MQTT to Telegram Rankings Bot using Docker.

## Prerequisites

- Docker Engine 20.10 or later
- Docker Compose V2 or later
- Git (to clone the repository)

## Quick Start

### 1. Setup Environment Variables

Copy the example environment file and configure it with your settings:

```bash
cp .env.docker.example .env
```

Edit `.env` and fill in your configuration:
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `TELEGRAM_CHAT_ID`: Your Telegram chat ID
- `HUMMINGBOT_API_PASSWORD`: Your Hummingbot API password
- Other settings as needed

### 2. Build and Run

Start the bot with Docker Compose:

```bash
docker-compose up -d
```

This will:
- Build the bot Docker image
- Start the MQTT broker (Mosquitto)
- Start the bot service
- Create necessary volumes for logs and data

### 3. Check Logs

View the bot logs:

```bash
# Follow logs in real-time
docker-compose logs -f mqtt-telegram-bot

# View MQTT broker logs
docker-compose logs -f mqtt-broker

# View all logs
docker-compose logs -f
```

### 4. Stop the Bot

Stop the running containers:

```bash
docker-compose down
```

To also remove volumes:

```bash
docker-compose down -v
```

## Docker Commands Reference

### Build the Image

Build or rebuild the Docker image:

```bash
docker-compose build
```

Force rebuild without cache:

```bash
docker-compose build --no-cache
```

### Run the Bot

Start services in detached mode:

```bash
docker-compose up -d
```

Start with logs visible:

```bash
docker-compose up
```

### View Status

Check running containers:

```bash
docker-compose ps
```

### Execute Commands in Container

Run commands inside the bot container:

```bash
# Open a shell in the container
docker-compose exec mqtt-telegram-bot /bin/bash

# Run Python directly
docker-compose exec mqtt-telegram-bot python -c "import sys; print(sys.version)"
```

### Update and Restart

Pull latest code and restart:

```bash
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

## Using External MQTT Broker

If you want to use an external MQTT broker instead of the included one:

1. Edit `.env` and set:
   ```
   MQTT_BROKER_HOST=your.mqtt.broker.com
   MQTT_BROKER_PORT=1883
   ```

2. Edit `docker-compose.yml` and comment out the mqtt-broker service and remove it from depends_on:
   ```yaml
   mqtt-telegram-bot:
     # ...
     # depends_on:
     #   - mqtt-broker
   ```

3. Start only the bot:
   ```bash
   docker-compose up -d mqtt-telegram-bot
   ```

## Using with Existing Hummingbot

### Local Hummingbot on Host

If Hummingbot is running on your host machine:

1. Set in `.env`:
   ```
   HUMMINGBOT_API_URL=http://host.docker.internal:8000
   ```

### Hummingbot in Another Container

If Hummingbot is in a Docker container on the same host:

1. Create a shared network:
   ```bash
   docker network create hummingbot-network
   ```

2. Edit `docker-compose.yml` and change the network to use the existing one:
   ```yaml
   networks:
     bot-network:
       external: true
       name: hummingbot-network
   ```

3. Set in `.env`:
   ```
   HUMMINGBOT_API_URL=http://hummingbot:8000
   ```
   (Replace `hummingbot` with your Hummingbot container name)

## Test Mode

Run the bot in test mode with automatic unwind:

```bash
docker-compose run --rm mqtt-telegram-bot python main_execution_bot.py --test-unwind --wait=180
```

## Production Deployment

For production use:

### 1. Security

- Configure MQTT authentication in `mosquitto/config/mosquitto.conf`
- Use strong passwords in `.env`
- Consider using Docker secrets for sensitive data
- Restrict network access with firewall rules

### 2. Monitoring

Set up monitoring and alerts:

```bash
# View resource usage
docker stats mqtt-telegram-bot

# Set up health checks
docker inspect --format='{{.State.Health.Status}}' mqtt-telegram-bot
```

### 3. Backup

Regularly backup your volumes:

```bash
# Backup logs
docker run --rm -v hb_mqtt_signal_tg_bot_logs:/backup \
  -v $(pwd)/backups:/backups alpine \
  tar czf /backups/logs-$(date +%Y%m%d).tar.gz -C /backup .
```

### 4. Auto-restart

The compose file includes `restart: unless-stopped` which will:
- Restart containers automatically after crashes
- Restart containers after host reboot
- Not restart containers you manually stopped

## Troubleshooting

### Bot Won't Start

Check logs:
```bash
docker-compose logs mqtt-telegram-bot
```

Common issues:
- Missing or invalid `.env` file
- MQTT broker not accessible
- Hummingbot API not accessible
- Invalid Telegram token

### MQTT Connection Issues

Test MQTT connectivity:
```bash
# Install mosquitto clients on host
apt-get install mosquitto-clients

# Test publish
mosquitto_pub -h localhost -t test -m "Hello"

# Test subscribe
mosquitto_sub -h localhost -t test
```

### Container Keeps Restarting

Check health status:
```bash
docker inspect mqtt-telegram-bot | grep -A 10 Health
```

View detailed logs:
```bash
docker logs mqtt-telegram-bot --tail 100
```

### Permission Issues

If you encounter permission issues with volumes:

```bash
# Fix ownership
sudo chown -R 1000:1000 logs/ data/
```

## Advanced Configuration

### Custom Dockerfile

If you need to modify the Dockerfile:

1. Edit `Dockerfile`
2. Rebuild: `docker-compose build`
3. Restart: `docker-compose up -d`

### Environment Variables

All environment variables from `.env.docker.example` are supported.

Key variables:
- `MQTT_BROKER_HOST`: MQTT broker hostname
- `TELEGRAM_BOT_TOKEN`: Bot token
- `TELEGRAM_CHAT_ID`: Where to send messages
- `HUMMINGBOT_API_URL`: Hummingbot API endpoint
- `TOTAL_TRADING_AMOUNT`: Total USD for trading
- `TOP_ASSETS_COUNT`: Number of long positions
- `BOTTOM_ASSETS_COUNT`: Number of short positions

### Resource Limits

Add resource limits in `docker-compose.yml`:

```yaml
mqtt-telegram-bot:
  # ...
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 512M
      reservations:
        memory: 256M
```

## Support

For issues or questions:
1. Check the logs: `docker-compose logs`
2. Review the `.env` configuration
3. Consult the main README.md
4. Check Docker and Docker Compose versions

## License

Same as the main project.
