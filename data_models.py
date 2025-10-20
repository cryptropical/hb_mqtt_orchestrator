"""
Data models and enumerations for MQTT Telegram Execution Bot
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Set


class BotState(Enum):
    """Bot instance states"""
    LAUNCHING = "launching"
    RUNNING = "running"
    UNWINDING = "unwinding"
    STOPPED = "stopped"
    ARCHIVED = "archived"


@dataclass
class AssetRanking:
    """Data class for asset ranking information"""
    trading_pair: str
    exchange: str
    price: float
    price_change_24h: float
    volume_avg_24h: float
    rank_score: float
    rank_position: int = 0
    v: float = 0.0
    v2: float = 0.0
    price_zscore: float = 0.0
    price_zscore2: float = 0.0


@dataclass
class RankingMessage:
    """Data class for the complete ranking message"""
    timestamp: float
    strategy_name: str
    controller_id: str
    rankings: List[AssetRanking]
    metadata: Dict[str, Any]
    top_assets: List[str] = field(default_factory=list)
    bottom_assets: List[str] = field(default_factory=list)
    new_top: Set[str] = field(default_factory=set)
    new_bottom: Set[str] = field(default_factory=set)
    old_top: Set[str] = field(default_factory=set)
    old_bottom: Set[str] = field(default_factory=set)


@dataclass
class TradingBot:
    """Data class for tracking trading bot instances"""
    instance_name: str
    base_asset: str
    side: str  # 'LONG' or 'SHORT'
    amount_quote: float
    status: BotState
    launch_time: float
    config_file: str = ""