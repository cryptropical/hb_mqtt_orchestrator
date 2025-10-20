"""
Trading orchestration module for MQTT Telegram Execution Bot
"""

import asyncio
import json
import logging
import time
import csv
import yaml
import requests
import os
import pandas as pd
from datetime import datetime
from typing import Dict, Set, Optional
import paho.mqtt.client as mqtt
from hummingbot_api_client import HummingbotAPIClient
from hyperliquid_margin_manager import HyperliquidMarginManager

from config import Config
from data_models import TradingBot, BotState, RankingMessage
from telegram_notifier import TelegramNotifier


class TradingOrchestrator:
    """Manages trading bot instances based on rankings"""
    
    def __init__(self, config: Config, hb_client: HummingbotAPIClient, telegram_notifier: TelegramNotifier):
        self.config = config
        self.hb_client = hb_client
        self.telegram = telegram_notifier
        self.logger = logging.getLogger(f"{__name__}.TradingOrchestrator")
        
        # Track active trading bots
        self.active_bots: Dict[str, TradingBot] = {}
        self.current_top_assets: Set[str] = set()
        self.current_bottom_assets: Set[str] = set()
        
        # Asset mapping dictionaries
        self.base_candles_ex_dict: Dict[str, str] = {}
        self.base_trading_ex_dict: Dict[str, str] = {}
        
        # Cooldown tracking for newly started bots
        self.bot_startup_times: Dict[str, float] = {}
        self.STARTUP_COOLDOWN = 30  # seconds to wait before checking bot status
        
        # Retry configuration
        self.MAX_API_RETRIES = 5
        self.API_RETRY_DELAY = 2  # seconds between retries

        #Initialize Hyperliquid margin manager
        try:
            margin_csv_path = getattr(config, 'margin_tiers_csv_path', 'hyperliquid_margin_tiers.csv')
            self.margin_manager = HyperliquidMarginManager(margin_csv_path)
            self.logger.info("Hyperliquid margin manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize margin manager: {e}")
            self.margin_manager = None
    
    async def initialize(self):
        """Initialize the trading orchestrator"""
        await self._setup_signal_monitor()
    
    async def _api_call_with_retry(self, api_call_func, *args, **kwargs):
        """Execute an API call with retry logic"""
        last_error = None
        for attempt in range(self.MAX_API_RETRIES):
            try:
                return await api_call_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                self.logger.warning(f"API call failed (attempt {attempt + 1}/{self.MAX_API_RETRIES}): {e}")
                if attempt < self.MAX_API_RETRIES - 1:
                    await asyncio.sleep(self.API_RETRY_DELAY)
                else:
                    raise last_error
    
    async def _setup_signal_monitor(self):
        """Setup and launch the signal monitoring instance"""
        try:
            # Check for existing instance with retry
            active_bots = await self._api_call_with_retry(
                self.hb_client.bot_orchestration.get_active_bots_status
            )
            
            if self.config.monitoring_instance_name in active_bots.get('data', {}).keys():
                self.logger.info(f"Stopping existing instance {self.config.monitoring_instance_name}")
                await self._api_call_with_retry(
                    self.hb_client.bot_orchestration.stop_and_archive_bot,
                    self.config.monitoring_instance_name, 
                    skip_order_cancellation=True
                )
                await asyncio.sleep(30)
            
            # Check for Top 100 CSV
            await self._ensure_top100_csv()
            
            # Build asset pairs mapping
            await self._build_asset_mappings()
            
            # Create and upload signal monitor config
            signal_config = await self._create_signal_monitor_config()
            
            # Upload config with retry and wait for registration
            await self._api_call_with_retry(
                self.hb_client.controllers.create_or_update_controller_config,
                config_name="signal_monitor_config",
                config=signal_config
            )
            
            # Wait for config to be registered
            await asyncio.sleep(3)
            self.logger.info("Config uploaded, waiting for registration...")
            
            # Deploy signal monitoring bot with retry
            result = await self._api_call_with_retry(
                self.hb_client.bot_orchestration.deploy_v2_controllers,
                instance_name=self.config.monitoring_instance_name,
                credentials_profile=self.config.credentials_profile,
                controllers_config=["signal_monitor_config.yml"],
                image=self.config.signal_monitor_hb_image
            )
            
            self.logger.info(f"Signal monitor launched: {result}")
            
            if self.config.verbose_telegram:
                await self.telegram.send_message(
                    f"🚀 <b>Signal Monitor Started</b>\n"
                    f"Instance: <code>{self.config.monitoring_instance_name}</code>\n"
                    f"Monitoring {len(self.base_candles_ex_dict)} pairs"
                )
            
        except Exception as e:
            self.logger.error(f"Error setting up signal monitor: {e}")
            raise
    
    async def _ensure_top100_csv(self):
        """Ensure Top 100 cryptocurrency CSV exists"""
        TOP100_CSV = "top100_by_marketcap.csv"
        
        if not os.path.exists(TOP100_CSV) and self.config.cmc_api_key:
            self.logger.info("Fetching Top 100 cryptocurrencies from CoinMarketCap")
            
            URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
            PARAMS = {"start": "1", "limit": "100", "convert": "USD"}
            HEADERS = {
                "Accept": "application/json",
                "X-CMC_PRO_API_KEY": self.config.cmc_api_key
            }
            
            try:
                resp = requests.get(URL, headers=HEADERS, params=PARAMS, timeout=30)
                resp.raise_for_status()
                coins = resp.json().get("data", [])
                
                headers = ["rank", "id", "name", "symbol", "price_usd", 
                          "market_cap_usd", "volume_24h_usd", "percent_change_24h"]
                
                with open(TOP100_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for coin in coins:
                        quote = coin.get("quote", {}).get("USD", {})
                        writer.writerow([
                            coin.get("cmc_rank"),
                            coin.get("id"),
                            coin.get("name"),
                            coin.get("symbol"),
                            quote.get("price"),
                            quote.get("market_cap"),
                            quote.get("volume_24h"),
                            quote.get("percent_change_24h"),
                        ])
                
                self.logger.info("Top 100 CSV created successfully")
            except Exception as e:
                self.logger.error(f"Error fetching Top 100: {e}")
    
    async def _build_asset_mappings(self):
        """Build asset name mappings between exchanges"""
        try:
            # Get trading rules with retry
            rules_candles = await self._api_call_with_retry(
                self.hb_client.connectors.get_trading_rules,
                self.config.candles_exchange
            )
            rules_trading = await self._api_call_with_retry(
                self.hb_client.connectors.get_trading_rules,
                self.config.trading_exchange
            )
            
            # Process candles exchange pairs
            quoted_pairs_candles = [p for p in rules_candles.keys() 
                                   if p.endswith(f"-{self.config.candles_quote}")]
            base_assets_candles = [p.split("-")[0] for p in quoted_pairs_candles]
            base_assets_candles_cleaned = [a.replace(self.config.base_extra_key_candles, "") 
                                          for a in base_assets_candles]
            
            # Process trading exchange pairs
            quoted_pairs_trading = [p for p in rules_trading.keys() 
                                   if p.endswith(f"-{self.config.trading_quote}")]
            base_assets_trading = [p.split("-")[0] for p in quoted_pairs_trading]
            base_assets_trading_cleaned = [a.replace(self.config.base_extra_key_trading, "")
                                          for a in base_assets_trading]

            # ensure BTC and ETH are included
            if 'BTC' not in base_assets_candles_cleaned:
                base_assets_candles_cleaned.append('BTC')
                base_assets_candles.append('BTC')
            if 'ETH' not in base_assets_candles_cleaned:
                base_assets_candles_cleaned.append('ETH')
                base_assets_candles.append('ETH')
            if 'BTC' not in base_assets_trading_cleaned:
                base_assets_trading_cleaned.append('BTC')
                base_assets_trading.append('BTC')
            if 'ETH' not in base_assets_trading_cleaned:
                base_assets_trading_cleaned.append('ETH')
                base_assets_trading.append('ETH')

            # remove blacklisted tokens listed in config
            for token in self.config.blacklisted_tokens:
                if token in base_assets_candles_cleaned:
                    idx = base_assets_candles_cleaned.index(token)
                    del base_assets_candles_cleaned[idx]
                    del base_assets_candles[idx]
                if token in base_assets_trading_cleaned:
                    idx = base_assets_trading_cleaned.index(token)
                    del base_assets_trading_cleaned[idx]
                    del base_assets_trading[idx]


            # Find common assets
            common_base_assets = set(base_assets_candles_cleaned) & set(base_assets_trading_cleaned)

            # Filter by Top 100 if available
            if os.path.exists("top100_by_marketcap.csv"):
                df = pd.read_csv("top100_by_marketcap.csv")
                top100 = df['symbol'].tolist()
                common_base_assets = common_base_assets.intersection(set(top100))

            # filtering by leverage
            # Filter by minimum leverage requirement
            if self.margin_manager and hasattr(self.config, 'minimum_leverage'):
                min_leverage = getattr(self.config, 'minimum_leverage', 1)
                network = getattr(self.config, 'margin_network', 'mainnet')

                self.logger.info(f"Filtering assets by minimum leverage: {min_leverage}x on {network}")

                # Test each asset with a small position to get max leverage
                test_position_size = 1000  # $1000 USD for testing
                filtered_assets = set()

                for asset in common_base_assets:
                    try:
                        # Get max leverage for this asset
                        max_leverage = self.margin_manager.get_max_leverage(asset, test_position_size, network)

                        if max_leverage is None:
                            # Asset not in margin tiers, assume leverage of 3
                            effective_leverage = 3
                            self.logger.info(f"Asset {asset} not in margin tiers, assuming 3x leverage")
                        else:
                            effective_leverage = max_leverage

                        # Check if it meets minimum requirement
                        if effective_leverage >= min_leverage:
                            filtered_assets.add(asset)
                            self.logger.debug(f"Asset {asset}: max leverage {effective_leverage}x - INCLUDED")
                        else:
                            self.logger.info(
                                f"Asset {asset}: max leverage {effective_leverage}x < {min_leverage}x - EXCLUDED")

                    except Exception as e:
                        self.logger.error(f"Error checking leverage for {asset}: {e}")
                        # In case of error, include the asset to be safe
                        filtered_assets.add(asset)

                common_base_assets = filtered_assets
                self.logger.info(f"After leverage filtering: {len(common_base_assets)} assets remain")


            # Create mapping dictionaries
            for asset in common_base_assets:
                if asset in base_assets_candles_cleaned:
                    idx = base_assets_candles_cleaned.index(asset)
                    self.base_candles_ex_dict[asset] = base_assets_candles[idx]

                if asset in base_assets_trading_cleaned:
                    idx = base_assets_trading_cleaned.index(asset)
                    self.base_trading_ex_dict[asset] = base_assets_trading[idx]

            # create a dataframe with the common assets as a index and two columns for each exchange
            self.mapping_df = pd.DataFrame(index=list(common_base_assets))
            self.mapping_df['candles_exchange'] = self.mapping_df.index.map(self.base_candles_ex_dict)
            self.mapping_df['trading_exchange'] = self.mapping_df.index.map(self.base_trading_ex_dict)

            self.logger.info(f"Built mappings for {len(common_base_assets)} common assets")

            # wait 1 minute to allow for cooldown of api calls to hyperliquid
            self.logger.info('Waiting 10 seconds to avoid rate limits...')
            await asyncio.sleep(10)
            
        except Exception as e:
            self.logger.error(f"Error building asset mappings: {e}")
            raise

    async def _create_signal_monitor_config(self) -> Dict:
        """Create signal monitor configuration"""
        # Load template
        with open("conf/signal_monitor_template.yml", 'r') as file:
            config = yaml.safe_load(file)
        
        # Create base assets string
        base_assets_str = ','.join([self.base_candles_ex_dict[asset] 
                                   for asset in self.base_candles_ex_dict.keys()])
        
        # Update configuration
        config.update({
            'candles_exchange': self.config.candles_exchange,
            'candles_quote_asset': self.config.candles_quote,
            'base_assets': base_assets_str,
            'n_pairs': max(self.config.monitor_top_count, self.config.monitor_bottom_count),
            'report_metrics': True,
            'report_candles': False,
            'kf_fast_gain': self.config.kf_fast_gain,
            'kf_slow_gain': self.config.kf_slow_gain,
            'kf_slower_gain': self.config.kf_slower_gain,
            'dbars_lookback': self.config.dbars_lookback,
            'candles_interval': self.config.candles_interval,
            'virtual_interval': self.config.virtual_interval,
            'filter_polarity': self.config.filter_polarity,
        })
        
        return config

    async def process_rankings(self, ranking_data: RankingMessage):
        """Process new rankings and manage bot instances"""
        try:
            # Re-rank and select top N for trading
            top_for_trading = ranking_data.top_assets[:self.config.top_assets_count]
            bottom_for_trading = ranking_data.bottom_assets[:self.config.bottom_assets_count]

            # Get the full monitor lists (buffer zones)
            top_monitor = set(ranking_data.top_assets[:self.config.monitor_top_count])
            bottom_monitor = set(ranking_data.bottom_assets[:self.config.monitor_bottom_count])

            if self.config.smart_close: # smart close logic

                # Check if current top assets are still within the top monitor buffer zone
                current_top_in_monitor = self.current_top_assets.intersection(top_monitor)
                current_top_out_of_monitor = self.current_top_assets - top_monitor
                current_bottom_in_monitor = self.current_bottom_assets.intersection(bottom_monitor)
                current_bottom_out_of_monitor = self.current_bottom_assets - bottom_monitor

                # Log the comparison results
                if current_top_out_of_monitor:
                    self.logger.info(f"Assets no longer in top monitor buffer: {current_top_out_of_monitor}")
                if current_top_in_monitor:
                    self.logger.info(f"Assets still in top monitor buffer: {current_top_in_monitor}")
                if current_bottom_out_of_monitor:
                    self.logger.info(f"Assets no longer in bottom monitor buffer: {current_bottom_out_of_monitor}")
                if current_bottom_in_monitor:
                    self.logger.info(f"Assets still in bottom monitor buffer: {current_bottom_in_monitor}")

                # new top and bottom are the new assets and the current in monitor
                top_for_trading = set(top_for_trading).union(current_top_in_monitor)
                bottom_for_trading = set(bottom_for_trading).union(current_bottom_in_monitor)



            # Convert to sets for comparison
            new_top = set(top_for_trading)
            new_bottom = set(bottom_for_trading)

            # Find changes
            assets_to_close_long = self.current_top_assets - new_top
            assets_to_close_short = self.current_bottom_assets - new_bottom
            assets_to_open_long = new_top - self.current_top_assets
            assets_to_open_short = new_bottom - self.current_bottom_assets

            # get the assets to change by name
            assets_to_close_long = self.mapping_df.index[self.mapping_df['candles_exchange'].isin(assets_to_close_long)].tolist()
            assets_to_close_short = self.mapping_df.index[self.mapping_df['candles_exchange'].isin(assets_to_close_short)].tolist()
            assets_to_open_long = self.mapping_df.index[self.mapping_df['candles_exchange'].isin(assets_to_open_long)].tolist()
            assets_to_open_short = self.mapping_df.index[self.mapping_df['candles_exchange'].isin(assets_to_open_short)].tolist()

            # Process closures (using gather to handle multiple closures concurrently)
            close_tasks = []
            for asset in assets_to_close_long:
                close_tasks.append(self._close_position(asset, 'LONG'))
            for asset in assets_to_close_short:
                close_tasks.append(self._close_position(asset, 'SHORT'))

            if close_tasks:
                results = await asyncio.gather(*close_tasks, return_exceptions=True)


            # Process new positions (using gather to handle multiple openings concurrently)
            amount_per_long = self.config.total_trading_amount / 2 / self.config.top_assets_count
            amount_per_short = self.config.total_trading_amount / 2 / self.config.bottom_assets_count

            open_tasks = []
            for asset in assets_to_open_long:
                open_tasks.append(self._open_position(asset, 'LONG', amount_per_long))
            for asset in assets_to_open_short:
                open_tasks.append(self._open_position(asset, 'SHORT', amount_per_short))

            if open_tasks:
                results = await asyncio.gather(*open_tasks, return_exceptions=True)
                # Log any errors from opening positions
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self.logger.error(f"Failed to open position: {result}")

            # Update current assets
            self.current_top_assets = new_top
            self.current_bottom_assets = new_bottom

            # Send summary to Telegram
            if assets_to_close_long or assets_to_close_short or assets_to_open_long or assets_to_open_short:
                await self.telegram.send_trading_summary(
                    assets_to_close_long, assets_to_close_short,
                    assets_to_open_long, assets_to_open_short
                )

        except Exception as e:
            self.logger.error(f"Error processing rankings: {e}", exc_info=True)
    
    async def _open_position(self, asset: str, side: str, amount: float):
        """Open a new trading position"""
        try:
            # Get trading pair format
            trading_base = self.base_trading_ex_dict.get(asset, asset)
            trading_pair = f"{trading_base}-{self.config.trading_quote}"
            
            # Create bot instance name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            instance_name = f"{asset}_{side}_{timestamp}"
            
            # Create TWAP config
            config = await self._create_twap_config(trading_pair, side, amount)
            config_name = f"twap_{instance_name}"
            
            # Upload config with retry
            try:
                await self._api_call_with_retry(
                    self.hb_client.controllers.create_or_update_controller_config,
                    config_name=config_name,
                    config=config
                )
                # Wait for config to be registered
                await asyncio.sleep(1)
                self.logger.info(f"Config {config_name} uploaded, waiting for registration...")
                
            except Exception as e:
                self.logger.error(f"Failed to upload config for {asset}: {e}")
                raise
            
            # Deploy bot with retry
            try:
                result = await self._api_call_with_retry(
                    self.hb_client.bot_orchestration.deploy_v2_controllers,
                    instance_name=instance_name,
                    credentials_profile=self.config.credentials_profile,
                    controllers_config=[f"{config_name}.yml"],
                    image=self.config.trading_hb_image
                )
                
                # Track startup time for cooldown
                self.bot_startup_times[instance_name] = time.time()
                
            except Exception as e:
                self.logger.error(f"Failed to deploy bot for {asset}: {e}")
                raise
            
            # Track bot
            bot = TradingBot(
                instance_name=instance_name,
                base_asset=asset,
                side=side,
                amount_quote=amount,
                status=BotState.LAUNCHING,  # Start with LAUNCHING status
                launch_time=time.time(),
                config_file=config_name
            )
            self.active_bots[instance_name] = bot
            
            self.logger.info(f"Opened {side} position for {asset}: {instance_name}")
            
            if self.config.verbose_telegram:
                await self.telegram.send_message(
                    f"📈 <b>Position Opened</b>\n"
                    f"Asset: <code>{asset}</code>\n"
                    f"Side: <code>{side}</code>\n"
                    f"Amount: ${amount:.2f}\n"
                    f"Instance: <code>{instance_name}</code>"
                )
            
        except Exception as e:
            self.logger.error(f"Error opening position for {asset}: {e}", exc_info=True)
    
    async def _close_position(self, asset: str, side: str):
        """Close an existing trading position"""
        try:
            # Find bot instance for this asset/side
            bot_to_close = None
            for instance_name, bot in self.active_bots.items():
                if bot.base_asset == asset and bot.side == side and bot.status in [BotState.RUNNING, BotState.LAUNCHING]:
                    bot_to_close = bot
                    break
            
            if not bot_to_close:
                self.logger.warning(f"No active bot found for {asset} {side}")
                return
            
            # Send unwind signal via MQTT
            trading_base = self.base_trading_ex_dict.get(asset, asset)
            trading_pair = f"{trading_base}-{self.config.trading_quote}"
            normalized_pair = trading_pair.replace("-", "_").lower()
            topic = f"{self.config.mqtt_control_topic}/{normalized_pair}/control_signals"
            
            mqtt_client = mqtt.Client()
            if self.config.mqtt_username and self.config.mqtt_password:
                mqtt_client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
            
            mqtt_client.connect(self.config.mqtt_broker_host, self.config.mqtt_broker_port)
            
            unwind_message = json.dumps({
                "action": "start_exit",
                "timestamp": time.time()
            })
            
            mqtt_client.publish(topic, unwind_message, qos=self.config.mqtt_qos)
            mqtt_client.disconnect()
            
            bot_to_close.status = BotState.UNWINDING
            
            self.logger.info(f"Sent unwind signal for {asset} {side}")
            
            # Monitor and archive after stopping
            asyncio.create_task(self._monitor_and_archive_bot(bot_to_close))
            
            if self.config.verbose_telegram:
                await self.telegram.send_message(
                    f"📉 <b>Position Closing</b>\n"
                    f"Asset: <code>{asset}</code>\n"
                    f"Side: <code>{side}</code>\n"
                    f"Instance: <code>{bot_to_close.instance_name}</code>"
                )
            
        except Exception as e:
            self.logger.error(f"Error closing position for {asset}: {e}")
    
    async def _monitor_and_archive_bot(self, bot: TradingBot):
        """Monitor bot until stopped then archive it"""
        try:
            max_wait = 120  # Maximum 2 minutes # this needs to be replaced using config parameters
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                active_bots = await self._api_call_with_retry(
                    self.hb_client.bot_orchestration.get_active_bots_status
                )
                bot_status = active_bots.get('data', {}).get(bot.instance_name, {})
                try: status = bot_status.get('general_logs')[-1].get('msg', False)
                except:
                    logging.error(f"Error getting general_logs for {bot.instance_name}")
                    status = False
                if status == 'Clock stopped successfully':
                    # Archive the bot
                    await self._api_call_with_retry(
                        self.hb_client.bot_orchestration.stop_and_archive_bot,
                        bot.instance_name
                    )
                    bot.status = BotState.ARCHIVED
                    
                    # Remove from active bots and startup times
                    if bot.instance_name in self.active_bots:
                        del self.active_bots[bot.instance_name]
                    if bot.instance_name in self.bot_startup_times:
                        del self.bot_startup_times[bot.instance_name]
                    
                    self.logger.info(f"Archived bot {bot.instance_name}")
                    break
                
                await asyncio.sleep(5)
            
        except Exception as e:
            self.logger.error(f"Error monitoring/archiving bot {bot.instance_name}: {e}")

    def _calculate_leverage_for_position(self, asset: str, position_size_usd: float) -> float:
        """
        Calculate optimal leverage for a position based on asset and size.

        Args:
            asset (str): Asset symbol
            position_size_usd (float): Position size in USD

        Returns:
            float: Optimal leverage to use
        """
        try:
            if not self.margin_manager:
                # Fallback to config leverage if margin manager not available
                return getattr(self.config, 'leverage', 10)

            network = getattr(self.config, 'margin_network', 'mainnet')
            use_optimal = getattr(self.config, 'use_optimal_leverage', True)
            risk_factor = getattr(self.config, 'leverage_risk_factor', 0.8)

            if use_optimal:
                # Use optimal leverage with safety margin
                leverage = self.margin_manager.get_optimal_leverage(
                    asset=asset,
                    notional_value=position_size_usd,
                    risk_factor=risk_factor,
                    network=network
                )
            else:
                # Use maximum leverage
                leverage = self.margin_manager.get_max_leverage(
                    asset=asset,
                    notional_value=position_size_usd,
                    network=network
                )

            if leverage is None:
                # Asset not in margin tiers, use assumed leverage of 3
                leverage = 3
                self.logger.info(f"Asset {asset} not in margin tiers, using 3x leverage")

            # Ensure leverage doesn't exceed config maximum
            max_config_leverage = getattr(self.config, 'max_leverage', 50)
            leverage = min(leverage, max_config_leverage)

            self.logger.info(f"Calculated leverage for {asset} (${position_size_usd:,.2f}): {leverage:.1f}x")
            return leverage

        except Exception as e:
            self.logger.error(f"Error calculating leverage for {asset}: {e}")
            # Fallback to config leverage
            return getattr(self.config, 'leverage', 10)


    async def _create_twap_config(self, trading_pair: str, side: str, amount: float) -> Dict:
        """Create TWAP trading configuration"""
        with open("conf/twap_order_trade_template.yml", 'r') as file:
            config = yaml.safe_load(file)

        # MODIFY THIS: Calculate dynamic leverage
        # Extract asset from trading pair
        asset = trading_pair.split('-')[0]
        # Remove any exchange-specific prefixes
        clean_asset = asset.replace(getattr(self.config, 'base_extra_key_trading', ''), '')

        # Calculate leverage for this position
        leverage = self._calculate_leverage_for_position(clean_asset, amount)

        config.update({
            'connector_name': self.config.trading_exchange,
            'trading_pair': trading_pair,
            'total_amount_quote': amount,
            'entry_side': 'BUY' if side == 'LONG' else 'SELL',
            'min_notional_size': self.config.min_notional_size,
            'batch_size_quote': self.config.batch_size_quote,
            'batch_interval': self.config.batch_interval,
            'leverage': leverage,
            'hold_duration_seconds': self.config.hold_duration_seconds,
            'test_mode': self.config.test_mode_trading,
            'notifications_topic': self.config.mqtt_control_topic,
        })
        
        return config
    
    async def unwind_all_positions(self):
        """Unwind all active trading positions"""
        self.logger.info("Starting to unwind all positions...")
        
        unwind_tasks = []
        for instance_name, bot in list(self.active_bots.items()):
            if bot.status in [BotState.RUNNING, BotState.LAUNCHING]:
                self.logger.info(f"Unwinding {bot.base_asset} {bot.side}")
                unwind_tasks.append(self._close_position(bot.base_asset, bot.side))
        
        if unwind_tasks:
            await asyncio.gather(*unwind_tasks, return_exceptions=True)
            
            # Wait for all bots to stop
            await self._wait_for_all_bots_stopped()
        
        self.logger.info("All positions unwound")
    
    async def _wait_for_all_bots_stopped(self, timeout: int = 180):
        """Wait for all bots to stop with a timeout"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if all bots are stopped or archived
            active_count = sum(1 for bot in self.active_bots.values() 
                             if bot.status not in [BotState.STOPPED, BotState.ARCHIVED])
            
            if active_count == 0:
                self.logger.info("All bots have stopped")
                break
            
            self.logger.info(f"Waiting for {active_count} bots to stop...")
            await asyncio.sleep(5)
        
        # Archive any remaining stopped bots
        for instance_name, bot in list(self.active_bots.items()):
            if bot.status == BotState.STOPPED:
                try:
                    await self._api_call_with_retry(
                        self.hb_client.bot_orchestration.stop_and_archive_bot,
                        instance_name
                    )
                    del self.active_bots[instance_name]
                except Exception as e:
                    self.logger.error(f"Error archiving bot {instance_name}: {e}")
    
    async def stop_all_bots(self):
        """Stop all active trading bots with unwinding"""
        # First unwind all positions
        await self.unwind_all_positions()
        
        # Then stop any remaining bots
        for instance_name, bot in list(self.active_bots.items()):
            try:
                await self._api_call_with_retry(
                    self.hb_client.bot_orchestration.stop_and_archive_bot,
                    instance_name
                )
                self.logger.info(f"Stopped bot {instance_name}")
            except Exception as e:
                self.logger.error(f"Error stopping bot {instance_name}: {e}")
    
    async def check_bot_health(self) -> Dict[str, str]:
        """Check health of active bots and return status summary"""
        health_status = {}
        try:
            active_bots = await self._api_call_with_retry(
                self.hb_client.bot_orchestration.get_active_bots_status
            )
            bot_data = active_bots.get('data', {})
            
            current_time = time.time()
            
            for instance_name, bot in self.active_bots.items():
                # Check if bot is in startup cooldown period
                startup_time = self.bot_startup_times.get(instance_name, 0)
                if current_time - startup_time < self.STARTUP_COOLDOWN:
                    # Bot is still starting up, update status if needed
                    if bot.status == BotState.LAUNCHING:
                        bot.status = BotState.RUNNING
                    health_status[instance_name] = 'starting'
                    continue
                
                # Check actual bot status
                if instance_name in bot_data:
                    status = bot_data[instance_name].get('status', 'unknown')
                    if status == 'stopped' and bot.status == BotState.RUNNING:
                        bot.status = BotState.STOPPED
                        health_status[instance_name] = 'stopped_unexpectedly'
                    else:
                        health_status[instance_name] = status
                else:
                    health_status[instance_name] = 'not_found'
            
        except Exception as e:
            self.logger.error(f"Error checking bot health: {e}")
        
        return health_status