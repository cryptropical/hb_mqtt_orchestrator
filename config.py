"""
Configuration management module for MQTT Telegram Execution Bot
"""

import os
from dotenv import load_dotenv


class TestModeOptions:
    DEV = 1
    STANDARD = 0


class Config:
    """Configuration manager for the bot"""
    
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # blacklisted tokens
        self.blacklisted_tokens = os.getenv('BLACKLISTED_TOKENS', 'USDT,USD,USDC,DAI,BUSD,UST,EURC,EUR,GBP,JPY,AUD,CAD,CHF').split(',')


        # Margin management settings
        self.margin_tiers_csv_path = os.getenv('MARGIN_TIERS_CSV_PATH', 'hyperliquid_margin_tiers.csv')
        self.margin_network = os.getenv('MARGIN_NETWORK', 'mainnet')
        self.minimum_leverage = float(os.getenv('MINIMUM_LEVERAGE', '5.0'))
        self.use_optimal_leverage = os.getenv('USE_OPTIMAL_LEVERAGE', 'true').lower() == 'true'
        self.leverage_risk_factor = float(os.getenv('LEVERAGE_RISK_FACTOR', '0.8'))
        self.max_leverage = float(os.getenv('MAX_LEVERAGE', '50.0'))
        
        # MQTT Configuration
        self.mqtt_broker_host = os.getenv('MQTT_BROKER_HOST', 'localhost')
        self.mqtt_broker_port = int(os.getenv('MQTT_BROKER_PORT', '1883'))
        self.mqtt_username = os.getenv('MQTT_USERNAME')
        self.mqtt_password = os.getenv('MQTT_PASSWORD')
        self.mqtt_topic = os.getenv('MQTT_TOPIC', 'ranking')
        self.mqtt_qos = int(os.getenv('MQTT_QOS', '1'))
        self.mqtt_control_topic = os.getenv('MQTT_CONTROL_TOPIC', 'hummmingbot/LS/notifications')
        
        # Telegram Configuration
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.verbose_telegram = os.getenv('VERBOSE_TELEGRAM', 'false').lower() == 'true'
        
        # Hummingbot API Configuration
        self.hb_api_url = os.getenv('HUMMINGBOT_API_URL', 'http://localhost:8000')
        self.hb_api_password = os.getenv('HUMMINGBOT_API_PASSWORD', 'admin')
        
        # Exchange Configuration
        self.candles_exchange = os.getenv('CANDLES_EXCHANGE', 'binance_perpetual')
        self.trading_exchange = os.getenv('TRADING_EXCHANGE', 'hyperliquid_perpetual')
        self.candles_quote = os.getenv('CANDLES_QUOTE', 'USDT')
        self.trading_quote = os.getenv('TRADING_QUOTE', 'USD')
        self.base_extra_key_trading = os.getenv('BASE_EXTRA_KEY_TRADING', 'k')
        self.base_extra_key_candles = os.getenv('BASE_EXTRA_KEY_CANDLES', '1000')
        
        # Bot Images
        self.signal_monitor_hb_image = os.getenv('SIGNAL_MONITOR_HB_IMAGE', '3mc/hummingbot:latest')
        self.trading_hb_image = os.getenv('TRADING_HB_IMAGE', 'hummingbot/hummingbot:latest')
        
        # Instance Names
        self.monitoring_instance_name = os.getenv('MONITORING_INSTANCE_NAME', 'LS_signal_monitoring')
        self.credentials_profile = os.getenv('CREDENTIALS_PROFILE', '3MC_testbed')
        
        # Trading Configuration
        self.total_trading_amount = float(os.getenv('TOTAL_TRADING_AMOUNT', '1000'))
        self.top_assets_count = int(os.getenv('TOP_ASSETS_COUNT', '5'))
        self.bottom_assets_count = int(os.getenv('BOTTOM_ASSETS_COUNT', '5'))
        self.monitor_top_count = int(os.getenv('MONITOR_TOP_COUNT', '8'))
        self.monitor_bottom_count = int(os.getenv('MONITOR_BOTTOM_COUNT', '8'))
        self.smart_close = os.getenv('SMART_CLOSE', 'close')
        
        # TWAP Configuration
        self.min_notional_size = float(os.getenv('MIN_NOTIONAL_SIZE', '12'))
        self.batch_size_quote = float(os.getenv('BATCH_SIZE_QUOTE', '15'))
        self.batch_interval = int(os.getenv('BATCH_INTERVAL', '15'))
        #self.leverage = int(os.getenv('LEVERAGE', '20'))
        self.hold_duration_seconds = int(os.getenv('HOLD_DURATION_SECONDS', '600'))
        self.test_mode_trading = os.getenv('TEST_MODE_TRADING', 'true').lower() == 'true'
        
        # Signal Monitor Configuration
        self.kf_slow_gain = float(os.getenv('KF_SLOW_GAIN', '0.1044'))
        self.kf_fast_gain = float(os.getenv('KF_FAST_GAIN', '0.441'))
        self.kf_slower_gain = float(os.getenv('KF_SLOWER_GAIN', '0.01'))
        self.dbars_lookback = os.getenv('DBARS_LOOKBACK', '14d')
        self.candles_interval = os.getenv('CANDLES_INTERVAL', '5m')
        self.virtual_interval = os.getenv('VIRTUAL_INTERVAL', '30m')
        self.filter_polarity = os.getenv('FILTER_POLARITY', 'true').lower() == 'true'
        
        # CMC API for Top 100
        self.cmc_api_key = os.getenv('CMC_API_KEY', '')
        
        # Bot Behavior Configuration
        self.update_interval = int(os.getenv('UPDATE_INTERVAL', '1'))
        self.enable_detailed_messages = os.getenv('ENABLE_DETAILED_MESSAGES', 'true').lower() == 'true'
        self.test_mode = int(os.getenv('TEST_MODE', TestModeOptions.STANDARD))
        
        # Validate required configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate that all required configuration is present"""
        if not self.telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in .env file")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required in .env file")