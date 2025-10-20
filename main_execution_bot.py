#!/usr/bin/env python3
"""
MQTT to Telegram Rankings Bot with Execution Layer

Main execution script that orchestrates all components for listening to MQTT rankings,
managing Hummingbot trading instances, and reporting to Telegram.
"""

import asyncio
import json
import logging
import sys
import signal
import time
from datetime import datetime
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt
from hummingbot_api_client import HummingbotAPIClient

# Import custom modules
from config import Config, TestModeOptions
from data_models import BotState
from telegram_notifier import TelegramNotifier
from trading_orchestrator import TradingOrchestrator
from mqtt_parser import MQTTMessageParser


# Configure logging
import os
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Create rotating file handler for log management
file_handler = RotatingFileHandler(
    'logs/mqtt_telegram_execution_bot.log',
    maxBytes=50*1024*1024,  # 50MB per log file
    backupCount=5,          # Keep 5 old log files
    encoding='utf-8'
)

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)

# Set formatters
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)


class MQTTRankingsExecutionBot:
    """Main MQTT to Telegram bot with execution capabilities"""
    
    def __init__(self, config: Config):
        self.config = config
        self.telegram = TelegramNotifier(config)
        self.mqtt_client = None
        self.hb_client = None
        self.orchestrator = None
        self.parser = MQTTMessageParser(config)
        self.logger = logging.getLogger(f"{__name__}.MQTTRankingsExecutionBot")
        self.last_update_time = 0
        self.running = False
        self.shutdown_in_progress = False
        self.test_unwind_mode = False  # Flag for test unwinding

    async def initialize(self):
        """Initialize all components with retry logic"""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Initializing MQTT Rankings Execution Bot (attempt {attempt + 1}/{max_retries})...")

                # Initialize Hummingbot API client
                self.hb_client = HummingbotAPIClient(
                    base_url=self.config.hb_api_url,
                    password=self.config.hb_api_password
                )
                await self.hb_client.init()
                self.logger.info("Hummingbot API client initialized")

                # Initialize Trading Orchestrator
                self.orchestrator = TradingOrchestrator(
                    self.config,
                    self.hb_client,
                    self.telegram
                )
                await self.orchestrator.initialize()
                self.logger.info("Trading orchestrator initialized")

                # Setup MQTT client
                self.setup_mqtt_client()
                self.logger.info("MQTT client configured")
                
                # Success - break out of retry loop
                break

            except Exception as e:
                self.logger.error(f"Error during initialization (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise
    
    def setup_mqtt_client(self):
        """Configure and setup the MQTT client"""
        self.mqtt_client = mqtt.Client()
        
        # Set credentials if provided
        if self.config.mqtt_username and self.config.mqtt_password:
            self.mqtt_client.username_pw_set(
                self.config.mqtt_username,
                self.config.mqtt_password
            )
        
        # Set callbacks
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.on_subscribe = self._on_mqtt_subscribe
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.logger.info("Connected to MQTT broker successfully")
            # Subscribe to the ranking topic
            client.subscribe(self.config.mqtt_topic, qos=self.config.mqtt_qos)
        else:
            self.logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.logger.info("Disconnected from MQTT broker")
    
    def _on_mqtt_subscribe(self, client, userdata, mid, granted_qos):
        """Callback for MQTT subscription"""
        self.logger.info(f"Subscribed to topic '{self.config.mqtt_topic}' with QoS {granted_qos}")

    def _on_mqtt_message(self, client, userdata, msg):
        """Callback for received MQTT messages"""
        try:
            # Skip processing if shutdown is in progress
            if self.shutdown_in_progress:
                self.logger.debug("Ignoring MQTT message during shutdown")
                return
                
            # Decode message payload
            payload = msg.payload.decode('utf-8')
            self.logger.debug(f"Received MQTT message on topic '{msg.topic}'")

            # Parse JSON data
            data = json.loads(payload)

            # Schedule async processing in the event loop
            if self.event_loop and not self.event_loop.is_closed():
                if self.config.test_mode == TestModeOptions.DEV:
                    asyncio.run_coroutine_threadsafe(
                        self._send_dev_mode_message(data),
                        self.event_loop
                    )
                else:
                    asyncio.run_coroutine_threadsafe(
                        self._process_ranking_data(data),
                        self.event_loop
                    )
            else:
                self.logger.error("Event loop not available for processing MQTT message")

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse MQTT message as JSON: {e}")
        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}")

    async def _send_dev_mode_message(self, data: dict):
        """Formats raw JSON data as a readable message and sends to Telegram"""
        try:
            formatted_data = self.parser.format_dev_mode_data(data)
            
            message_lines = ["🔧 <b>DEV MODE DATA</b>", ""]
            for key, value in formatted_data.items():
                message_lines.append(f"<b>{key}:</b> <code>{value}</code>")
            
            message_text = "\n".join(message_lines)
            
            success = await self.telegram.send_message(message_text)
            if success:
                self.logger.info("Successfully sent dev mode message to Telegram")
            else:
                self.logger.warning("Failed to send dev mode message to Telegram")
                
        except Exception as e:
            self.logger.error(f"Error sending dev mode message: {e}")

    async def _process_ranking_data(self, data: Dict[str, Any]):
        """Process incoming ranking data and trigger trading actions"""
        try:
            # Skip processing if shutdown is in progress
            if self.shutdown_in_progress:
                self.logger.debug("Ignoring ranking data during shutdown")
                return
                
            # Check rate limiting
            current_time = datetime.now().timestamp()
            if current_time - self.last_update_time < self.config.update_interval:
                self.logger.debug("Skipping update due to rate limiting")
                return
            
            # Parse the ranking data
            ranking_message = self.parser.parse_ranking_data(data)
            if not ranking_message:
                self.logger.warning("Failed to parse ranking message")
                return
            
            # Send ranking update to Telegram
            if (self.config.enable_detailed_messages or 
                ranking_message.new_top or ranking_message.new_bottom):
                formatted_message = self.telegram.format_ranking_message(ranking_message)
                await self.telegram.send_message(formatted_message)
            
            # Process rankings for trading (skip if in test unwind mode)
            if not self.test_unwind_mode:
                await self.orchestrator.process_rankings(ranking_message)
            
            self.last_update_time = current_time
            self.logger.info("Successfully processed ranking update")
                
        except Exception as e:
            self.logger.error(f"Error processing ranking data: {e}")
    
    async def start(self):
        """Start the MQTT to Telegram bot"""
        self.logger.info("Starting MQTT to Telegram Rankings Execution Bot")
        
        try:
            # Store the current event loop
            self.event_loop = asyncio.get_running_loop()
            
            # Initialize components
            await self.initialize()
            
            # Connect to MQTT broker
            self.mqtt_client.connect(
                self.config.mqtt_broker_host,
                self.config.mqtt_broker_port,
                60
            )
            
            # Send startup notification
            await self.telegram.send_startup_message(self.config)
            
            # Start MQTT loop
            self.running = True
            self.mqtt_client.loop_start()
            
            # Periodic status checks
            while self.running:
                await asyncio.sleep(45)
                await self._check_bot_health()
                
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")
            await self.stop()
    
    async def _check_bot_health(self):
        """Periodic health check of active bots"""
        try:
            if not self.orchestrator or self.shutdown_in_progress:
                return
            
            health_status = await self.orchestrator.check_bot_health()
            
            # Report any unexpected stops (but not during startup)
            for instance_name, status in health_status.items():
                if status == 'stopped_unexpectedly':
                    bot = self.orchestrator.active_bots.get(instance_name)
                    if bot and self.config.verbose_telegram:
                        await self.telegram.send_message(
                            f"⚠️ <b>Bot Stopped Unexpectedly</b>\n"
                            f"Instance: <code>{instance_name}</code>\n"
                            f"Asset: {bot.base_asset} ({bot.side})"
                        )
                elif status == 'starting':
                    self.logger.debug(f"Bot {instance_name} is still starting up")
            
        except Exception as e:
            self.logger.error(f"Error in health check: {e}")

    async def test_unwind_all(self, wait_time: int = 180):
        """Test mode: Wait for bots to trade, then unwind all positions

        Args:
            wait_time: Seconds to wait after all bots are RUNNING before unwinding
        """
        self.logger.info(f"Starting TEST MODE: Will unwind after {wait_time}s of trading")
        self.test_unwind_mode = True

        try:
            # First, check if we have any bots to test
            if not self.orchestrator.active_bots:
                await self.telegram.send_message(
                    "⚠️ <b>No Active Bots</b>\n\n"
                    "There are no active bots to test unwind. "
                    "Please wait for some positions to open first."
                )
                return

            # Wait for all bots to be in RUNNING state
            await self.telegram.send_message(
                "🧪 <b>TEST MODE: Preparing Unwind Test</b>\n\n"
                "1️⃣ Waiting for all bots to be fully active..."
            )

            all_running = await self._wait_for_all_bots_running(timeout=120)

            if not all_running:
                await self.telegram.send_message(
                    "⚠️ <b>Some bots didn't start properly</b>\n\n"
                    "Not all bots reached RUNNING state. Check logs for details."
                )
                return

            bot_count = len(self.orchestrator.active_bots)
            await self.telegram.send_message(
                f"✅ All {bot_count} bots are now RUNNING\n\n"
                f"2️⃣ Waiting {wait_time} seconds for bots to trade..."
            )

            # Wait for the specified time with periodic updates
            update_interval = min(60, wait_time // 3)
            elapsed = 0

            while elapsed < wait_time:
                remaining = wait_time - elapsed
                if elapsed > 0 and elapsed % update_interval == 0:
                    await self.telegram.send_message(
                        f"⏱ <b>Test Progress</b>\n"
                        f"Elapsed: {elapsed}s / {wait_time}s\n"
                        f"Remaining: {remaining}s"
                    )

                await asyncio.sleep(1)
                elapsed += 1

                # Check if bots are still healthy
                if elapsed % 30 == 0:
                    health_status = await self.orchestrator.check_bot_health()
                    stopped_count = sum(1 for status in health_status.values()
                                        if status == 'stopped_unexpectedly')
                    if stopped_count > 0:
                        self.logger.warning(f"{stopped_count} bots stopped unexpectedly during wait")

            # Now start the unwind process
            await self.telegram.send_message(
                "🔄 <b>Starting Unwind Process</b>\n\n"
                f"3️⃣ Unwinding {len(self.orchestrator.active_bots)} positions..."
            )

            # Unwind all positions
            await self.orchestrator.unwind_all_positions()

            await self.telegram.send_message(
                "✅ <b>Test Unwind Complete</b>\n\n"
                f"Successfully unwound and archived all positions after {wait_time}s of trading."
            )

            self.logger.info("Test unwind completed successfully")

        except Exception as e:
            self.logger.error(f"Error during test unwind: {e}")
            await self.telegram.send_message(
                f"❌ <b>Test Unwind Failed</b>\n\n"
                f"Error: {e}"
            )
        finally:
            self.test_unwind_mode = False

    async def _wait_for_all_bots_running(self, timeout: int = 120) -> bool:
        """Wait for all bots to reach RUNNING state

        Returns:
            bool: True if all bots are running, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            active_bots = await self.orchestrator._api_call_with_retry(
                self.orchestrator.hb_client.bot_orchestration.get_active_bots_status
            )
            bot_data = active_bots.get('data', {})

            all_running = True
            launching_count = 0

            for instance_name, bot in self.orchestrator.active_bots.items():
                if instance_name in bot_data:
                    api_status = bot_data[instance_name].get('status')

                    if api_status == 'running' and bot.status != BotState.RUNNING:
                        bot.status = BotState.RUNNING
                        self.logger.info(f"Bot {instance_name} is now RUNNING")
                    elif api_status != 'running':
                        all_running = False
                        if bot.status == BotState.LAUNCHING:
                            launching_count += 1
                else:
                    all_running = False
                    if bot.status == BotState.LAUNCHING:
                        launching_count += 1

            if all_running:
                self.logger.info("All bots are now in RUNNING state")
                return True

            self.logger.info(f"Waiting for {launching_count} bots to become active...")
            await asyncio.sleep(5)

        self.logger.warning(f"Timeout waiting for all bots to reach RUNNING state")
        return False
    
    async def stop(self, graceful=True):
        """Stop the bot with optional graceful shutdown"""
        if self.shutdown_in_progress:
            self.logger.info("Shutdown already in progress")
            return
            
        self.shutdown_in_progress = True
        self.logger.info(f"Stopping MQTT to Telegram Rankings Execution Bot (graceful={graceful})")
        
        self.running = False
        
        # Send shutdown notification
        await self.telegram.send_message(
            "🛑 <b>Bot Shutdown Initiated</b>\n\n"
            f"Mode: {'Graceful (unwinding positions)' if graceful else 'Immediate'}"
        )
        
        # Stop MQTT client first to prevent new messages
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.logger.info("MQTT client disconnected")
        
        # Handle trading bots based on graceful flag
        if self.orchestrator:
            if graceful:
                self.logger.info("Gracefully unwinding all positions before shutdown...")
                await self.orchestrator.stop_all_bots()  # This unwinds then archives
            else:
                self.logger.info("Immediate shutdown - archiving bots without unwinding...")
                # Just archive without unwinding
                for instance_name in list(self.orchestrator.active_bots.keys()):
                    try:
                        await self.orchestrator.hb_client.bot_orchestration.stop_and_archive_bot(instance_name)
                    except Exception as e:
                        self.logger.error(f"Error archiving bot {instance_name}: {e}")
        
        # Send final shutdown notification
        await self.telegram.send_shutdown_message()
        
        self.logger.info("Shutdown complete")
        self.shutdown_in_progress = False


async def main():
    """Main application entry point"""
    bot = None
    
    # Check for command line arguments
    test_mode = "--test-unwind" in sys.argv
    
    # Parse wait time for test mode (default 180 seconds)
    wait_time = 180
    for arg in sys.argv:
        if arg.startswith("--wait="):
            try:
                wait_time = int(arg.split("=")[1])
            except ValueError:
                logger.warning(f"Invalid wait time: {arg}, using default 180s")
    
    try:
        # Load configuration
        config = Config()
        logger.info("Configuration loaded successfully")
        
        # Create the bot instance
        bot = MQTTRankingsExecutionBot(config)
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            if bot and not bot.shutdown_in_progress:
                # Schedule graceful shutdown
                asyncio.create_task(bot.stop(graceful=True))
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Check if running in test mode
        if test_mode:
            logger.info(f"Running in TEST UNWIND mode with {wait_time}s wait time")
            # Initialize the bot
            bot.event_loop = asyncio.get_running_loop()
            await bot.initialize()
            
            # Connect MQTT to receive rankings
            bot.mqtt_client.connect(
                config.mqtt_broker_host,
                config.mqtt_broker_port,
                60
            )
            bot.mqtt_client.loop_start()
            
            # Wait for some positions to open first
            await bot.telegram.send_message(
                "🧪 <b>Test Mode Started</b>\n\n"
                "Waiting for positions to open from rankings..."
            )
            
            # Wait for positions to be created
            while len(bot.orchestrator.active_bots) == 0:
                await asyncio.sleep(5)
                logger.info("Waiting for positions to open...")
            
            # Run test unwind with specified wait time
            await bot.test_unwind_all(wait_time=wait_time)
            
            # Cleanup
            bot.mqtt_client.loop_stop()
            bot.mqtt_client.disconnect()
            
            # Exit after test
            logger.info("Test mode completed, exiting")
            sys.exit(0)
        else:
            # Normal operation
            await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down gracefully...")
        if bot:
            await bot.stop(graceful=True)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        if bot:
            try:
                await bot.stop(graceful=False)
            except:
                pass
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())