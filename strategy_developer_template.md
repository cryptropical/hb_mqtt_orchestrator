# Strategy Developer Template - Long/Short Momentum Trading System

## Overview

**Strategy Name**: Automated market monitoring & bot orchestration for long/short momentum trading on perpetual futures

**Strategy Type**: Directional Trading

**Complexity**: Advanced

**Status**: Production Ready

## Summary

An automated trading system that combines three interconnected components to execute momentum-based trading signals from 
a broad market monitoring on perpetual futures markets. 
The system uses candles feed from exchange 1 (Binance) to peform technical analysis on a pre-filtered list of common 
assets between two exchanges and to trigger signals via mqtt. The orchestrator automatically launch bots in a second 
exchange (e.g. Hyperliquid) which automatically manages the positions using a custom TWAP execution for entry and exit.

## Architecture

### Component 1: Signal Monitoring Bot (Screener)
**Controller Name**: `screener_v3`
**Type**: Screener Controller

A Hummingbot controller that continuously monitors multiple cryptocurrency pairs and ranks them based on momentum 
indicators using Kalman filtering.

**Key Features**:
- Multi-timeframe momentum analysis
- Volume-bar based data aggregation for volume-weighted analysis
- Z-score normalization for price and acceleration metrics
- Bollinger Bands width and percentage tracking
- Normalized Average True Range (NATR) for volatility measurement
- Real-time ranking of assets based on composite momentum scores
- MQTT reporting for downstream systems

**Technical Indicators**:
- `price_zscore`: Z-score of price (short-term)
- `price_zscore2`: Z-score of price (longer-term)
- `v`: momentum velocity metric
- `v2`: Secondary velocity metric
- `a_zscore`: Acceleration z-score
- `bbands_width_pct`: Bollinger Bands width percentage
- `bbands_percentage`: Position within Bollinger Bands
- `natr`: Normalized Average True Range
- `price_%ret`: Price percentage return
- `percentile_%ret`: Percentile ranking of returns



### Component 2: TWAP Order Trade Controller
**Controller Name**: `twap_order_trade`
**Type**: Directional Trading Controller

A custom Hummingbot controller that executes trades using Time-Weighted Average Price (TWAP) methodology, 
breaking large orders into smaller batches to minimize market impact.

**Key Features**:
- Configurable batch sizing and timing
- Support for MARKET LIMIT, and LIMIT_CHASER execution modes (uses OrderExecutor)
- Automatic retry mechanism for failed batches
- Configurable hold duration for test mode
- Position lifecycle management (entry → hold → exit)
- Fallback to market orders for remaining amounts
- Leverage support for perpetual contracts
- MQTT integration for remote control

**Configuration Parameters**:
```yaml
# Trading Parameters
total_amount_quote: 27          # USD amount per trade
entry_side: BUY/SELL           # Trade direction
min_notional_size: 12          # Minimum order size
leverage: 20                   # Trading leverage

# TWAP Configuration
batch_size_quote: 15           # Max batch size in USD
batch_interval: 15             # Seconds between batches
execution_strategy: MARKET     # MARKET/LIMIT/LIMIT_CHASER
price_buffer_pct: 0.0025      # 0.25% buffer for limits

# Lifecycle
hold_duration_seconds: 600     # Hold time before exit
test_mode: true               # Auto-exit mode
max_retries_per_batch: 3      # Retry attempts
```

**Execution Flow**:
1. **Entry Phase**: Splits total amount into batches based on min notional size and batch size
2. **Hold Phase**: Maintains position for configured duration (test mode) or until external signal
3. **Exit Phase**: Reverses position using same TWAP methodology
4. **Fallback**: Market orders for unfilled amounts after max retries

### Component 3: MQTT Orchestrator & Telegram Execution Bot
**Type**: Orchestration Layer

A Python application that coordinates the entire trading system, managing Hummingbot instances, processing signals, 
and providing notifications. It leverages the MQTT implementation for inter-component communication and bot orchestration.

**Key Features**:
- Automated deployment of signal monitoring instances
- Real-time MQTT message processing
- Smart position management based on rankings
- Multi-exchange support with asset naming translation
- Health monitoring of all active bots
- Configurable Telegram notifications (verbose/minimal)
- Graceful shutdown with position cleanup
- Top 100 cryptocurrency filtering (via CoinMarketCap API)
- Asset mapping between exchanges

**Position Management Logic**:
- **Long Positions**: Opens for top N ranked assets
- **Short Positions**: Opens for bottom N ranked assets
- **Re-ranking**: Filters to trading count (e.g., monitor top 8, trade top 5)
- **Closing**: Sends MQTT signals when assets leave monitored range
- **Monitoring**: Tracks bot states (LAUNCHING, RUNNING, UNWINDING, STOPPED, ARCHIVED)

**Configuration Parameters**:
```bash
# Trading Configuration
TOTAL_TRADING_AMOUNT=1000       # Total USD allocation
LONG_ASSETS_COUNT=5              # Long positions
SHORT_ASSETS_COUNT=5           # Short positions

# TWAP Execution
MIN_NOTIONAL_SIZE=12            # Minimum order size
BATCH_SIZE_QUOTE=15             # Batch size
BATCH_INTERVAL=15               # Batch interval (seconds)
LEVERAGE=20                     # Trading leverage

# Hold Configuration
HOLD_DURATION_SECONDS=600       # Auto-exit timer (test mode)
TEST_MODE_TRADING=true          # Enable test mode

# Exchange Configuration
CANDLES_EXCHANGE=binance_perpetual   # Data source
CANDLES_QUOTE=USDT
TRADING_EXCHANGE=hyperliquid_perpetual  # Execution venue
TRADING_QUOTE=USD
```

## System Workflow

### 1. Initialization
1. Check for existing signal monitor instances (stops if running)
2. Download Top 100 cryptocurrencies by market cap (optional)
3. Build asset mapping dictionaries between exchanges
4. Deploy signal monitoring bot with configured parameters
5. Connect to MQTT broker
6. Initialize Telegram notifications

### 2. Signal Processing Loop
1. Receive signal updates via MQTT (includes top/bottom assets with detailed metrics for testing purposes)
2. Identify changes in top/bottom rankings
3. Determine positions to open/close

### 3. Position Management
**Opening Positions**:
- Calculate position size per asset (equal allocation)
- Verify minimum notional size
- Translate asset names between exchanges
- Create TWAP controller configuration with:
  - Trading pair (translated to execution exchange format)
  - Total amount (position size)
  - Entry side (LONG for top, SHORT for bottom)
  - Leverage, batch size, interval
- Deploy new Hummingbot instance
- Track in orchestrator state

**Closing Positions**:
- Detect when close signal is received for a trading asset
- Send MQTT control signal to trigger exit
- Monitor unwinding process
- Archive bot when stopped

### 4. Health Monitoring
- Periodic checks of all active trading bots
- Status reporting via Telegram
- Automatic cleanup of failed instances

### 5. Reporting
**Verbose Mode** (detailed):
- Full report of signals with all metrics
- Position changes with amounts and leverage
- Bot status changes
- Health check results


## Technical Requirements

### Infrastructure
- **Hummingbot**: v2 framework with controller support
- **MQTT Broker**: Mosquitto, EMQX, or similar
- **Python**: 3.8+
- **Telegram Bot**: For notifications

### Exchange Requirements
- **Data Source**: Exchange with perpetual futures (e.g., Binance Perpetual)
- **Execution**: Perpetual DEX or CEX (e.g., Hyperliquid, Binance, Bybit)
- **Features**: Leverage support, API for bot deployment

### Network
- Stable internet connection
- Low latency to exchanges
- MQTT broker accessibility

## Risk Management

### Position Sizing
- Fixed USD amount per position
- Equal allocation for total trading amount
- Dynamic adjustment based on number of positions
- Configurable leverage (default: 20x)
- Minimum notional size enforcement

### Entry/Exit Controls
- TWAP execution reduces market impact
- Configurable batch sizes and intervals
- Price buffer for limit orders
- Retry mechanism with fallback to market orders
- Automatic exit after hold duration (test mode)


## Performance Considerations

### Latency
- MQTT messaging: ~100ms
- Hummingbot API calls: ~200-500ms
- Position deployment: ~2-5 seconds
- Total signal-to-execution: ~3-10 seconds

### Scalability
- Supports up to 20 concurrent trading bots (configurable)
- Asset universe: Tested with 100+ pairs
- Update frequency: Configurable (default: every ranking update)

### Resource Usage
- CPU: Light (< 5% per bot on modern systems)
- Memory: ~100-200MB per Hummingbot instance
- Network: Moderate (continuous WebSocket connections)

## Future Enhancements

### Planned Features
- Dynamic position sizing based on volatility
- Multi-timeframe confirmation
- Portfolio-level stop loss
- Correlation-based pair filtering
- Machine learning ranking enhancement
- Advanced risk metrics dashboard

### Optimization Opportunities
- Order book analysis for better entry timing
- Adaptive batch sizing based on volume
- Cross-exchange arbitrage detection
- Gas fee optimization for DEX execution

## Author Information

**Creator**: @cryptr0pical
**Version**: 0.9.0
**Last Updated**: Sep 2025
uture results.