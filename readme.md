# MQTT to Telegram Rankings Bot with Execution Layer

A sophisticated automated trading bot that monitors asset rankings via MQTT, manages Hummingbot trading instances, and reports activities through Telegram. The bot automatically opens and closes positions based on momentum signals from a ranking system.

## 🚀 Features

- **Automated Signal Monitoring**: Deploys and manages a Hummingbot instance for real-time asset ranking
- **Smart Position Management**: Automatically opens long/short positions based on rankings
- **Dynamic Portfolio Rebalancing**: Closes positions when assets leave the top/bottom rankings
- **Multi-Exchange Support**: Handles different asset naming conventions across exchanges
- **MQTT Integration**: Receives ranking updates and sends control signals via MQTT
- **Telegram Notifications**: Real-time updates with configurable verbosity levels
- **Health Monitoring**: Periodic checks on all active trading bots
- **Graceful Shutdown**: Properly closes all positions and archives bots on exit

## 📋 Prerequisites

- Python 3.8 or higher
- Access to a Hummingbot API server
- MQTT broker (e.g., Mosquitto, EMQX)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- (Optional) CoinMarketCap API key for Top 100 filtering

## 🛠 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/mqtt-telegram-rankings-bot.git
cd mqtt-telegram-rankings-bot
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: If `hummingbot-api-client` is not available on PyPI, install from source:
```bash
pip install git+https://github.com/hummingbot/hummingbot-api-client.git
```

### 4. Configure Environment

Copy the environment template and fill in your values:

```bash
cp env_template.sh .env
```

Edit `.env` with your configuration:

```bash
# Required configurations
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
HUMMINGBOT_API_URL=http://localhost:8000
HUMMINGBOT_API_PASSWORD=your_api_password
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883

# Trading parameters
TOTAL_TRADING_AMOUNT=1000
TOP_ASSETS_COUNT=5
BOTTOM_ASSETS_COUNT=5
LEVERAGE=20
```

### 5. Set Up Configuration Templates

Create a `conf/` directory with the required templates:

```bash
mkdir conf
cp templates/signal_monitor_template.yml conf/
cp templates/twap_order_trade_template.yml conf/
```

## 📁 Project Structure

```
hb_mqtt_signal_tg_bot/
│
├── mqtt_telegram_execution_bot.py  # Main execution script
├── config.py                        # Configuration management
├── data_models.py                   # Data classes and enums
├── telegram_notifier.py             # Telegram notification handler
├── trading_orchestrator.py          # Trading bot orchestration
├── mqtt_parser.py                   # MQTT message parsing
│
├── conf/                            # Configuration templates
│   ├── signal_monitor_template.yml
│   └── twap_order_trade_template.yml
│
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables (create from template)
├── .gitignore                      # Git ignore file
└── README.md                       # This file
```

## 🚀 Usage

### Basic Usage

Run the bot with default settings:

```bash
python mqtt_telegram_execution_bot.py
```

### Development Mode

Enable development mode to see raw MQTT data:

```bash
TEST_MODE=1 python mqtt_telegram_execution_bot.py
```

### Docker Deployment (Optional)

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "mqtt_telegram_execution_bot.py"]
```

Build and run:

```bash
docker build -t mqtt-rankings-bot .
docker run -d --env-file .env mqtt-rankings-bot
```

## ⚙️ Configuration

### Key Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTAL_TRADING_AMOUNT` | Total USD amount for trading | 1000 |
| `TOP_ASSETS_COUNT` | Number of top assets to trade long | 5 |
| `BOTTOM_ASSETS_COUNT` | Number of bottom assets to trade short | 5 |
| `LEVERAGE` | Trading leverage | 20 |
| `VERBOSE_TELEGRAM` | Enable detailed Telegram messages | false |
| `UPDATE_INTERVAL` | Minimum seconds between ranking updates | 1 |

### Exchange Configuration

Configure exchange-specific parameters for handling different asset naming:

```bash
# Candles/monitoring exchange
CANDLES_EXCHANGE=binance_perpetual
CANDLES_QUOTE=USDT
BASE_EXTRA_KEY_CANDLES=1000  # For assets like 1000BONK

# Trading execution exchange
TRADING_EXCHANGE=hyperliquid_perpetual
TRADING_QUOTE=USD
BASE_EXTRA_KEY_TRADING=k  # For assets like kBONK
```

## 📊 How It Works

1. **Initialization**
   - Checks for existing signal monitor instances
   - Downloads Top 100 cryptocurrencies (if configured)
   - Builds asset mappings between exchanges
   - Deploys signal monitoring bot

2. **Ranking Reception**
   - Listens to MQTT for ranking updates
   - Parses messages containing top/bottom performers
   - Identifies changes in rankings

3. **Position Management**
   - Opens long positions for top N assets
   - Opens short positions for bottom N assets
   - Sends MQTT control signals to close positions when assets leave rankings
   - Monitors and archives stopped bots

4. **Reporting**
   - Sends formatted updates to Telegram
   - Reports position changes and bot health
   - Provides detailed metrics in verbose mode

## 🔧 Development

### Running Tests

```bash
python -m pytest tests/
```

### Linting

```bash
flake8 *.py
black *.py
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 Logging

The bot creates detailed logs in `mqtt_telegram_execution_bot.log`. Monitor logs:

```bash
tail -f mqtt_telegram_execution_bot.log
```

Log levels can be adjusted in the main script's logging configuration.

## 🔒 Security Considerations

- Never commit `.env` files with actual credentials
- Use environment variables for sensitive data
- Implement rate limiting for API calls
- Use secure MQTT connections (TLS) in production
- Regularly rotate API keys and tokens

## 🐛 Troubleshooting

### Common Issues

**MQTT Connection Failed**
- Verify broker is running: `mosquitto_sub -t '#' -v`
- Check firewall settings
- Confirm credentials if authentication is enabled

**Hummingbot API Connection Error**
- Ensure Hummingbot API server is running
- Verify API URL and password
- Check network connectivity

**Telegram Messages Not Sending**
- Verify bot token is correct
- Ensure chat ID is properly formatted
- Check bot has permissions in the target chat

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🤝 Support

- Create an [Issue](https://github.com/yourusername/mqtt-telegram-rankings-bot/issues) for bug reports
- Start a [Discussion](https://github.com/yourusername/mqtt-telegram-rankings-bot/discussions) for questions
- Check [Wiki](https://github.com/yourusername/mqtt-telegram-rankings-bot/wiki) for detailed documentation

## 🙏 Acknowledgments

- [Hummingbot](https://hummingbot.io/) for the trading infrastructure
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for Telegram integration
- [Eclipse Paho](https://www.eclipse.org/paho/) for MQTT client

## ⚠️ Disclaimer

This bot is for educational purposes. Trading cryptocurrencies carries significant risk. Always:
- Test thoroughly in paper trading mode first
- Start with small amounts
- Never trade more than you can afford to lose
- Understand the risks of leveraged trading
- Monitor your positions regularly

---

**Version**: 1.0.0  
**Author**: Cryptropical 
**Last Updated**: September 2025
