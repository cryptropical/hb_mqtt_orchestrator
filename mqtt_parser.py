"""
MQTT message parsing module for MQTT Telegram Execution Bot
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from data_models import RankingMessage, AssetRanking


class MQTTMessageParser:
    """Parses MQTT messages into structured data"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.MQTTMessageParser")
    
    def parse_ranking_data(self, data: Dict[str, Any]) -> Optional[RankingMessage]:
        """Parse raw ranking data from MQTT into structured format"""
        try:
            # Extract timestamp
            timestamp = data.get('timestamp', datetime.now().timestamp())
            if isinstance(timestamp, str):
                # Parse ISO format timestamp
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.timestamp()
            
            # Create ranking message
            ranking_message = RankingMessage(
                timestamp=timestamp,
                strategy_name=data.get('strategy_name', 'Unknown'),
                controller_id=data.get('controller_id', 'Unknown'),
                rankings=[],
                metadata=data.get('metadata', {}),
                top_assets=data.get('top_assets', []),
                bottom_assets=data.get('bottom_assets', []),
                new_top=set(data.get('new_top', [])),
                new_bottom=set(data.get('new_bottom', [])),
                old_top=set(data.get('old_top', [])),
                old_bottom=set(data.get('old_bottom', []))
            )
            
            # Parse detailed rankings if available
            if 'detailed_top_assets' in data:
                self._parse_detailed_assets(
                    data['detailed_top_assets'], 
                    ranking_message, 
                    is_top=True
                )
            
            if 'detailed_bottom_assets' in data:
                self._parse_detailed_assets(
                    data['detailed_bottom_assets'], 
                    ranking_message, 
                    is_top=False
                )
            
            return ranking_message
            
        except Exception as e:
            self.logger.error(f"Error parsing ranking data: {e}")
            return None
    
    def _parse_detailed_assets(self, detailed_data: Dict, ranking_message: RankingMessage, is_top: bool):
        """Parse detailed asset information"""
        for asset, details in detailed_data.items():
            ranking = AssetRanking(
                trading_pair=f"{asset}-{self.config.candles_quote}",
                exchange=self.config.candles_exchange,
                price=details.get('price', 0),
                price_change_24h=details.get('price_%ret', 0) * 100,
                volume_avg_24h=details.get('volume_avg_24h', 0),
                rank_score=details.get('v2', 0),
                rank_position=details.get('rank', 0),
                v=details.get('v', 0),
                v2=details.get('v2', 0),
                price_zscore=details.get('price_zscore', 0),
                price_zscore2=details.get('price_zscore2', 0)
            )
            ranking_message.rankings.append(ranking)
    
    def format_dev_mode_data(self, data: dict) -> Dict[str, str]:
        """Format raw data for dev mode display"""
        formatted = {}
        
        # Extract key fields for display
        key_fields = ['timestamp', 'type', 'top_assets', 'bottom_assets', 
                     'new_top', 'new_bottom', 'old_top', 'old_bottom']
        
        for key in key_fields:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    # Limit list display to first 5 items
                    value = ', '.join(str(v) for v in value[:5])
                    if len(data[key]) > 5:
                        value += f" ... ({len(data[key])} total)"
                formatted[key] = str(value)
        
        return formatted