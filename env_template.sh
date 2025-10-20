# MQTT to Telegram Rankings Bot with Execution Layer Configuration
# Copy this file to .env and fill in your actual values

# =============================================================================
# MQTT Configuration
# =============================================================================

# MQTT Broker connection details
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883

# MQTT authentication (optional)
MQTT_USERNAME=
MQTT_PASSWORD=

# MQTT topic to subscribe to for ranking messages
MQTT_TOPIC=ranking

# MQTT topic for control signals
MQTT_CONTROL_TOPIC=hummmingbot/LS/notifications

# MQTT Quality of Service level (0, 1, or 2)
MQTT_QOS=1

# =============================================================================
# Telegram Configuration
# =============================================================================

# Telegram Bot Token (get from @BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Telegram Chat ID where messages will be sent
TELEGRAM_CHAT_ID=your_chat_id_here

# Enable verbose Telegram messages (true/false)
# true = detailed activity logs, false = minimal notifications
VERBOSE_TELEGRAM=false

# =============================================================================
# Hummingbot API Configuration
# =============================================================================

# Hummingbot API endpoint
HUMMINGBOT_API_URL=http://localhost:8000

# Hummingbot API password
HUMMINGBOT_API_PASSWORD=admin

# =============================================================================
# Exchange Configuration
# =============================================================================

# Exchange for candles/monitoring data
CANDLES_EXCHANGE=binance_perpetual
# Quote asset for candles exchange
CANDLES_QUOTE=USDT
# Base asset prefix/suffix for candles (e.g., '1000' for 1000BONK-USDT)
BASE_EXTRA_KEY_CANDLES=1000

# Exchange for trading execution
TRADING_EXCHANGE=hyperliquid_perpetual
# Quote asset for trading exchange
TRADING_QUOTE=USD
# Base asset prefix/suffix for trading (e.g., 'k' for kBONK-USD)
BASE_EXTRA_KEY_TRADING=k

# =============================================================================
# Bot Images Configuration
# =============================================================================

# Docker image for signal monitoring bot
SIGNAL_MONITOR_HB_IMAGE=3mc/hummingbot:latest

# Docker image for trading bots
TRADING_HB_IMAGE=hummingbot/hummingbot:latest

# =============================================================================
# Instance Configuration
# =============================================================================

# Name for the signal monitoring instance
MONITORING_INSTANCE_NAME=LS_signal_monitoring

# Credentials profile for bot deployment
CREDENTIALS_PROFILE=3MC_testbed

# =============================================================================
# Trading Configuration
# =============================================================================

# Total USD amount to allocate for trading
# This will be split equally between long and short positions
TOTAL_TRADING_AMOUNT=1000

# Number of top assets to trade long
TOP_ASSETS_COUNT=5

# Number of bottom assets to trade short
BOTTOM_ASSETS_COUNT=5

# Number of top assets to monitor (should be >= TOP_ASSETS_COUNT)
MONITOR_TOP_COUNT=8

# Number of bottom assets to monitor (should be >= BOTTOM_ASSETS_COUNT)
MONITOR_BOTTOM_COUNT=8

# =============================================================================
# TWAP Execution Configuration
# =============================================================================

# Minimum order size in USD
MIN_NOTIONAL_SIZE=12

# Maximum batch size for TWAP orders in USD
BATCH_SIZE_QUOTE=15

# Time between TWAP order batches (seconds)
BATCH_INTERVAL=15

# Trading leverage
LEVERAGE=20

# How long to hold position before auto-exit (seconds)
# Only applies when TEST_MODE_TRADING=true
HOLD_DURATION_SECONDS=600

# Enable test mode for trading (auto-exit after hold duration)
TEST_MODE_TRADING=true

# =============================================================================
# Signal Monitor Configuration (Kalman Filter)
# =============================================================================

# Kalman filter gains
KF_SLOW_GAIN=0.1044
KF_FAST_GAIN=0.441
KF_SLOWER_GAIN=0.01

# Dollar bars lookback period
DBARS_LOOKBACK=14d

# Candle interval for data collection
CANDLES_INTERVAL=5m

# Virtual interval for signal processing
VIRTUAL_INTERVAL=30m

# =============================================================================
# CoinMarketCap API (Optional)
# =============================================================================

# API key for fetching Top 100 cryptocurrencies by market cap
# Get from https://coinmarketcap.com/api/
CMC_API_KEY=

# =============================================================================
# Bot Behavior Configuration
# =============================================================================

# Minimum interval between ranking updates (seconds)
UPDATE_INTERVAL=1

# Enable detailed messages with metadata (true/false)
ENABLE_DETAILED_MESSAGES=true

# Test mode (0=STANDARD, 1=DEV)
# DEV mode shows raw MQTT data in Telegram
TEST_MODE=0

# =============================================================================
# Example Values (for reference)
# =============================================================================

# Example for local Hummingbot setup:
# HUMMINGBOT_API_URL=http://localhost:8000
# MQTT_BROKER_HOST=localhost
# MQTT_BROKER_PORT=1883
# MQTT_TOPIC=ranking
# MQTT_CONTROL_TOPIC=hummmingbot/LS/notifications

# Example for cloud setup:
# HUMMINGBOT_API_URL=http://10.147.19.3:8000
# MQTT_BROKER_HOST=10.147.19.3
# MQTT_BROKER_PORT=1883
# MQTT_USERNAME=admin
# MQTT_PASSWORD=your_password

# Example Telegram configuration:
# TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
# TELEGRAM_CHAT_ID=@your_channel or -1001234567890

# Example trading amounts:
# TOTAL_TRADING_AMOUNT=1000  # $1000 total
# TOP_ASSETS_COUNT=5          # 5 long positions = $100 each
# BOTTOM_ASSETS_COUNT=5       # 5 short positions = $100 each