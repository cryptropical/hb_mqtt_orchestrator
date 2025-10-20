"""
Telegram notification module for MQTT Telegram Execution Bot
"""

import logging
from datetime import datetime, timezone
from telegram import Bot
from telegram.error import TelegramError
from config import Config
from data_models import RankingMessage


class TelegramNotifier:
    """Handles Telegram message sending"""
    
    def __init__(self, config: Config):
        self.config = config
        self.bot = Bot(token=config.telegram_token)
        self.logger = logging.getLogger(f"{__name__}.TelegramNotifier")

    async def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Send a message to the configured Telegram chat"""
        max_length = 4096
        success = True

        while message:
            if len(message) <= max_length:
                chunk = message
                message = ""
            else:
                split_index = message.rfind('\n', 0, max_length)
                if split_index == -1:
                    split_index = max_length
                chunk = message[:split_index]
                message = message[split_index:].lstrip('\n')

            try:
                await self.bot.send_message(
                    chat_id=self.config.telegram_chat_id,
                    text=chunk,
                    parse_mode=parse_mode
                )
                self.logger.debug("Successfully sent message chunk to Telegram")
            except Exception as e:
                self.logger.error(f"Error sending Telegram message: {e}")
                success = False

        return success

    def format_ranking_message(self, ranking_data: RankingMessage) -> str:
        """Format ranking data into a readable Telegram message"""
        try:
            dt = datetime.fromtimestamp(ranking_data.timestamp, tz=timezone.utc)
            timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            lines = [
                "🎯 <b>Asset Rankings Update</b>",
                f"📅 {timestamp_str}",
                ""
            ]
            
            # Show top performers for trading
            if ranking_data.top_assets:
                top_trading = ranking_data.top_assets[:self.config.top_assets_count]
                lines.append(f"🚀 <b>Long Positions ({len(top_trading)})</b>")
                for i, asset in enumerate(top_trading, 1):
                    lines.append(f"{i}. <code>{asset}</code>")
                lines.append("")
            
            # Show bottom performers for trading
            if ranking_data.bottom_assets:
                bottom_trading = ranking_data.bottom_assets[:self.config.bottom_assets_count]
                lines.append(f"📉 <b>Short Positions ({len(bottom_trading)})</b>")
                for i, asset in enumerate(bottom_trading, 1):
                    lines.append(f"{i}. <code>{asset}</code>")
                lines.append("")
            
            # Show changes if verbose
            #TODO: change to use the actual processed data from the trading_orchestrator
            if self.config.verbose_telegram:
                if ranking_data.new_top:
                    lines.append(f"✅📈 New in Top monitoring: {', '.join(ranking_data.new_top)}")
                if ranking_data.old_top:
                    lines.append(f"❌📈 Exit in Top monitoring: {', '.join(ranking_data.old_top)}")
                if ranking_data.new_bottom:
                    lines.append(f"✅📉 New in Bottom monitoring: {', '.join(ranking_data.new_bottom)}")
                if ranking_data.old_bottom:
                    lines.append(f"❌📉 Exit in Bottom monitoring: {', '.join(ranking_data.old_bottom)}")
                lines.append("")
            
            # Add detailed metrics if available and enabled
            if self.config.enable_detailed_messages and ranking_data.rankings:
                lines.append("📊 <b>Top Metrics</b>")
                for ranking in ranking_data.rankings[:self.config.monitor_top_count]:
                    asset = ranking.trading_pair.split('-')[0]
                    if ranking.v2 >= 0:
                        lines.append(
                            f"• <b>{asset}</b>: "
                            f"v2={ranking.v2:.3f}, v={ranking.v:.3f}, "
                            f"zscore={ranking.price_zscore:.2f}"
                        )
                lines.append("📊 <b>Bottom Metrics</b>")
                for ranking in ranking_data.rankings[-self.config.monitor_bottom_count:]:
                    asset = ranking.trading_pair.split('-')[0]
                    if ranking.v2 <=0:
                        lines.append(
                            f"• <b>{asset}</b>: "
                            f"v2={ranking.v2:.3f}, v={ranking.v:.3f}, "
                            f"zscore={ranking.price_zscore:.2f}"
                        )
            
            return "\n".join(lines)
            
        except Exception as e:
            self.logger.error(f"Error formatting ranking message: {e}")
            return f"⚠️ Error formatting ranking data: {e}"

    async def send_startup_message(self, config: Config):
        """Send bot startup notification"""
        startup_message = (
            "🤖 <b>Rankings Execution Bot Started</b>\n\n"
            f"📡 MQTT Broker: {config.mqtt_broker_host}:{config.mqtt_broker_port}\n"
            f"📢 Topic: <code>{config.mqtt_topic}</code>\n"
            f"💰 Total Amount: ${config.total_trading_amount}\n"
            f"📈 Top Assets: {config.top_assets_count}\n"
            f"📉 Bottom Assets: {config.bottom_assets_count}\n"
            f"🔧 Min Leverage: {config.minimum_leverage}\n"
            f"🔧 Optimal Leverage: {config.use_optimal_leverage}\n\n"
            f"🎯 Smart close: {config.smart_close}"
            "✅ Ready to execute trades!"
        )
        return await self.send_message(startup_message)

    async def send_shutdown_message(self):
        """Send bot shutdown notification"""
        shutdown_message = (
            "🛑 <b>Rankings Execution Bot Stopped</b>\n\n"
            "All trading bots have been gracefully shut down."
        )
        return await self.send_message(shutdown_message)

    async def send_trading_summary(self, closed_long, closed_short, opened_long, opened_short):
        """Send trading activity summary"""
        lines = ["🔄 <b>Trading Activity Update</b>", ""]
        
        if closed_long:
            lines.append(f"📈❌ <b>Closed Long:</b> {', '.join(closed_long)}")
        if opened_long:
            lines.append(f"📈✅ <b>Opened Long:</b> {', '.join(opened_long)}")
        if closed_short:
            lines.append(f"📈❌ <b>Closed Short:</b> {', '.join(closed_short)}")
        if opened_short:
            lines.append(f"📉✅ <b>Opened Short:</b> {', '.join(opened_short)}")
        
        return await self.send_message("\n".join(lines))