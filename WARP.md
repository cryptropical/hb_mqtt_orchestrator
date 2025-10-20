# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is an MQTT to Telegram Rankings Bot with automated trading execution capabilities. The bot monitors asset rankings via MQTT, manages Hummingbot trading instances, and provides real-time notifications through Telegram. It automatically opens and closes positions based on momentum signals from a Kalman filter-based ranking system.

## Common Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Hummingbot API client if not available on PyPI
pip install git+https://github.com/hummingbot/hummingbot-api-client.git

# Setup environment configuration
cp env_template.sh .env
# Edit .env with your actual values
```

### Running the Application
```bash
# Standard mode
python main_execution_bot.py

# Development mode (shows raw MQTT data)
TEST_MODE=1 python main_execution_bot.py

# With specific environment variables
VERBOSE_TELEGRAM=true python main_execution_bot.py
```

### Development and Testing
```bash
# Run linting
flake8 *.py

# Format code
black *.py

# Run tests (if available)
python -m pytest tests/

# Monitor logs
tail -f mqtt_telegram_execution_bot.log
```

### Configuration Management
```bash
# Create configuration directory
mkdir conf

# Copy configuration templates
cp templates/signal_monitor_template.yml conf/
cp templates/twap_order_trade_template.yml conf/
```

## Architecture Overview

The system follows a modular, event-driven architecture with the following key components:

### Core Components

1. **`main_execution_bot.py`** - Main orchestrator that:
   - Initializes all system components
   - Manages MQTT client and event loop
   - Handles graceful shutdown with signal handlers
   - Coordinates between ranking processing and trading execution

2. **`trading_orchestrator.py`** - Trading logic engine that:
   - Deploys and manages Hummingbot signal monitoring instances
   - Builds asset mapping between different exchanges (candles vs trading)
   - Opens/closes positions based on ranking changes using concurrent processing
   - Monitors bot health and handles bot lifecycle (launching → running → unwinding → archived)

3. **`mqtt_parser.py`** - Message processing layer that:
   - Parses JSON ranking data from MQTT messages
   - Converts raw data into structured `RankingMessage` objects
   - Handles both simple ranking updates and detailed asset metrics

4. **`telegram_notifier.py`** - Communication interface that:
   - Formats ranking updates into readable messages
   - Handles message chunking for Telegram's 4096 character limit
   - Provides different verbosity levels for notifications

5. **`config.py`** - Configuration management that:
   - Loads environment variables with sensible defaults
   - Validates required configurations on startup
   - Provides centralized access to all bot parameters

6. **`data_models.py`** - Data structures defining:
   - `BotState` enum for tracking bot lifecycle states
   - `AssetRanking` dataclass for individual asset metrics
   - `RankingMessage` dataclass for complete ranking updates
   - `TradingBot` dataclass for tracking active trading instances

### Key Design Patterns

- **Async/Await**: All I/O operations use asyncio for concurrent processing
- **Event-Driven**: MQTT messages trigger async processing chains
- **State Management**: Bot states are tracked through enum-based lifecycle
- **Separation of Concerns**: Each module has a single, well-defined responsibility
- **Configuration-Driven**: Behavior is controlled through environment variables
- **Error Handling**: Comprehensive exception handling with logging

### Data Flow

1. **Signal Monitor Deployment**: Trading orchestrator deploys Hummingbot instances for monitoring
2. **MQTT Rankings**: External ranking system publishes asset rankings via MQTT
3. **Message Processing**: MQTT parser converts raw messages to structured data
4. **Trading Decisions**: Orchestrator compares new rankings with current positions
5. **Position Management**: Opens new positions and closes existing ones via Hummingbot API
6. **Notifications**: Telegram notifier sends updates about trading activities

### Exchange Integration

The system handles multi-exchange scenarios by maintaining mapping dictionaries:
- **Candles Exchange**: Used for data collection and ranking (e.g., Binance with USDT quotes)
- **Trading Exchange**: Used for actual trading execution (e.g., Hyperliquid with USD quotes)
- **Asset Mapping**: Handles different naming conventions (e.g., 1000BONK-USDT vs kBONK-USD)

### Configuration Templates

- **`signal_monitor_template.yml`**: Kalman filter configuration for ranking generation
- **`twap_order_trade_template.yml`**: TWAP execution parameters for position entry/exit

## Important Environment Variables

Key variables that significantly affect behavior:
- `TEST_MODE`: 0=STANDARD, 1=DEV (shows raw MQTT data)
- `TEST_MODE_TRADING`: Enable auto-exit after hold duration
- `VERBOSE_TELEGRAM`: Enable detailed Telegram notifications
- `TOTAL_TRADING_AMOUNT`: Total USD allocated for trading
- `TOP_ASSETS_COUNT`/`BOTTOM_ASSETS_COUNT`: Number of positions to maintain
- `LEVERAGE`: Trading leverage multiplier

## Development Notes

- The system requires both Hummingbot API server and MQTT broker to be running
- Bot instances are managed through Hummingbot's orchestration API
- Position sizing is automatically calculated based on total trading amount
- The system handles graceful shutdown by closing all active positions
- Health checks run periodically to monitor bot status
- All trading actions are logged for audit trails

## File Structure Patterns

- Main execution logic in root directory
- Configuration templates in `conf/` directory
- Environment configuration in `.env` (created from `env_template.sh`)
- Logs written to `mqtt_telegram_execution_bot.log`
