import logging
from decimal import Decimal
import json
from typing import Any, Dict

import numpy as np
import pandas as pd
from pandas import DataFrame
from pydantic import Field, field_validator
from typing import Dict, List, Optional, Set, Tuple

import hummingbot
from hummingbot.client.config.config_data_types import ClientFieldData
from hummingbot.data_feed.candles_feed.candles_factory import CandlesConfig, CandlesFactory
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.strategy_v2.controllers.directional_trading_controller_base import (
    DirectionalTradingControllerBase,
    DirectionalTradingControllerConfigBase,
)
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase as sb
from hummingbot.strategy_v2.models.executor_actions import ExecutorAction
from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.remote_iface.mqtt import ETopicPublisher

from tmc_lib.Klaman import KF
from tmc_lib.candles_util import DataUtil

import pandas_ta as ta  # noqa: F401

TG_VERBOSE = True


class TestModeOptions:
    ALWAYS_REBALANCE = 1
    STANDARD = 0
    ALWAYS_SELL = -1


class KalmanFilterNewtoninan(ControllerConfigBase):
    controller_type: str = "screener"
    controller_name: str = "Kalman_filter_newtonian_screener_v3"
    columns_to_show: List[str] = ["trading_pair", "price_zscore", "price_zscore2", 'v', "v2", 'price_%ret',
                                  "percentile_%ret",
                                  "a_zscore", "bbands_width_pct", "bbands_percentage", "natr"]

    columns_to_report: List[str] = ["rank", "base", "v2", "v"]
    sort_values_by: List[str] = ['v2', "v", "price_zscore2", "price_zscore", "natr", "bbands_width_pct",
                                 "bbands_percentage"]

    connector_name: str = Field(
        default="hyperliquid_perpetual",
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Exchange where the bot will trade (e.g., kraken):",
        },
    )
    candles_exchange: str = Field(
        default="binance_perpetual",
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Exchange where the candles data will be fetched (e.g., kraken):",
        },
    )
    candles_config: List[CandlesConfig] = []
    total_amount_quote: Decimal = 100

    candles_quote_asset: str = Field(
        default="USDT",
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the target quote asset for the candles:"
        },
    )

    n_pairs: int = Field(
        default=10,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the number of trading pairs to trade per side: ",
        },
    )

    ## MQTT Configuration ##
    mqtt_topic_prefix: str = Field(
        default="hummingbot/screener/ranking",
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the MQTT topic prefix for publishing screener data: ",
        },
    )

    enable_mqtt_publishing: bool = Field(
        default=True,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enable MQTT publishing for screener results? (True/False): ",
        },
    )

    ## Data source parameters: Trading pairs and filtering##
    base_assets: str = Field(
        default='AAVE,BNB,BNT,BTC,ETC,ETH,FET,FIL',
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter comma-separated base assets to use for the screener (e.g., AAVE,BNB,BNT,BTC,ETC,ETH,FET,FIL): ",
        },
    )
    max_lev_filt: int = Field(  # max leverage for filtering the list
        default=100,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the maximum leverage for filtering the list: ",
        },
    )
    min_lev_filt: int = Field(  # min leverage for filtering the list
        default=10,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the minimum leverage for filtering the list: ",
        },
    )
    ## Data feed parameters ##
    dbars: bool = Field(  # use dbars
        default=True,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Use dbars? (True/False): ",
        },
    )
    virtual_interval: str = Field(
        default='4h',
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the virtual interval to sample the $Bars (e.g., 1m, 5m, 1h, 1d): ",
        },
    )
    candles_interval: str = Field(
        default="30m",
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the candle interval from where the $bars will be re-sampled (at least 1/4 of virtual interval): ",
        },
    )
    dbars_lookback: str = Field(
        default='1w',
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the virtual interval to sample the $Bars (e.g., 1m, 5m, 1h, 1d): ",
        },
    )

    ## Strategy parameters ##
    volatility_interval: int = Field(
        default=50,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the interval (N bars) to compute the volatility make sure max_record * monitoring_interval / virtual_interval >> volatility_interval: ",
        },
    )
    trend_interval: int = Field(
        default=50,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the interval (N bars) to compute the trend max_record * monitoring_interval / virtual_interval >> trend_interval: ",
        },
    )
    pct_change_interval: int = Field(
        default=8,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the interval (N bars) to compute the percentile of %return in a given period : ",
        },
    )
    # Kalman filter parameters #
    kf_slow_gain: float = Field(
        default=0.075,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the slow gain for the Kalman filter (typically <0.01): ",
        },
    )
    kf_slower_gain: float = Field(
        default=0.05,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the slower gain for the Kalman filter (typically <0.01): ",
        },
    )
    kf_fast_gain: float = Field(
        default=0.15,
        gt=0,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Enter the fast gain for the Kalman filter (typically 0.1-0.5): ",
        },
    )

    report_metrics: bool = Field(
        default=False,
        json_schema_extra={
        "prompt_on_new": True,
        "prompt": "Report metrics in MQTT publishing? (True/False): "
        },
    )

    report_candles: bool = Field(
        default=False,
        json_schema_extra={
        "prompt_on_new": True,
        "prompt": "Report candles in MQTT publishing? (True/False): "
        },
    )

    filter_polarity: bool = Field(
        default=True,
        json_schema_extra={
            "prompt_on_new": True,
            "prompt": "Filter assets based on polarity of v and v2? (True/False): ",
        },
    )

    max_records: int = 1000
    n_records2dbars: int = 1000  # This will be calculated based on dbars_lookback and candles_interval

    def update_markets(self, markets: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
        if self.connector_name not in markets:
            markets[self.connector_name] = set()
        markets[self.connector_name].add('BTC-USDT')  # mock connector
        return markets


class KalmanFilterNewtoninanController(ControllerBase):
    _logger = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger('Screener controller')
        return cls._logger

    def __init__(self, config: KalmanFilterNewtoninan, *args, **kwargs):

        self.report_metrics = config.report_metrics
        self.report_candles = config.report_candles

        # Calculate records before calling super().__init__
        self.n_records2dbars = int(DataUtil.get_seconds_from_interval(
            config.dbars_lookback) / DataUtil.get_seconds_from_interval(config.candles_interval))

        self.max_records = int(self.n_records2dbars + 10)

        # Update config with calculated values
        config.max_records = self.max_records
        config.n_records2dbars = self.n_records2dbars

        # Update candles_config with correct max_records
        base_assets_list = [base.strip() for base in config.base_assets.split(",") if
                            base.strip()]
        config.candles_config = [
            CandlesConfig(
                connector=config.candles_exchange,
                trading_pair=base_asset + config.candles_quote_asset,
                interval=config.candles_interval,
                max_records=self.max_records,
                dbars=config.dbars,
                n_records2dbars=self.n_records2dbars,
                virtual_interval=config.virtual_interval
            )
            for base_asset in base_assets_list
        ]
        #
        ## Try to enable MQTT autostart before calling super().__init__
        try:
            # Access the app through various possible paths
            self._app = HummingbotApplication.main_application()
            if not self._app.client_config_map.mqtt_bridge.mqtt_autostart:
                self.mqtt_pub = None
                raise AttributeError("MQTT autostart is not enabled")

            else:
                self.mqtt_pub = ETopicPublisher(config.mqtt_topic_prefix, use_bot_prefix=False)
                self.logger().info("MQTT autostart enabled for screener publishing")

        #    if hasattr(app, 'client_config_map') and hasattr(app.client_config_map, 'mqtt_bridge'):
        #        app.client_config_map.mqtt_bridge.mqtt_autostart = True
        #        self.logger().info("MQTT autostart enabled for screener publishing")

        except Exception as e:
            #    # Don't fail initialization if MQTT setup fails
            self.logger().info(f"Could not enable MQTT autostart: {str(e)}")


        super().__init__(config, *args, **kwargs)

        # Initialize other attributes
        self.config = config
        self.base_assets = base_assets_list

        # Initialize candles dictionary and last_timestamp tracking
        self.candles = {}
        self.candles_started = False

        # Initialize other existing attributes...
        self.raking_updated = False
        self.dbars_updated = False
        self.market_status_metrics_df = None
        self.metrics_updated = None
        self.config = config
        self.config.max_records = self.max_records
        self.config.n_records2dbars = self.n_records2dbars

        self.base_dir = str(hummingbot.root_path())
        self.top = None
        self.bottom = None
        self.df_comparison = None
        self.last_time_reported = 0
        self.dbars = config.dbars
        self.candles_interval = config.candles_interval
        self.fast_gain = config.kf_fast_gain
        self.slow_gain = config.kf_slow_gain
        self.slower_gain = config.kf_slower_gain
        self.volatility_interval = config.volatility_interval
        self.trend_interval = config.trend_interval
        self.pct_change_interval = config.pct_change_interval
        self.market_analysis_initialized = False
        self.virtual_interval = config.virtual_interval
        self.notifications = None  # we will use this to send notifications to the main strategy and post them to the app
        if TG_VERBOSE:
            self.notifications = "HL Long/Short Screener started!"



    def publish_mqtt_ranking(self, new_top: List[str] = None, new_bottom: List[str] = None,
                                old_top: List[str] = None, old_bottom: List[str] = None):
        """
        Publish the current top and bottom rankings to MQTT broker
        """
        if not self.config.enable_mqtt_publishing:
            return

        try:
            # Get MQTT gateway from the application
            # publisher = self.mqtt_pub

            if self.mqtt_pub is None or not self._app._mqtt.health:
                self.logger().warning("MQTT gateway not available or not healthy")
                return

            report_keys = ["v2", "v", "price_zscore", "price_zscore2", "bbands_width_pct", "bbands_percentage", "natr",
                           "price_%ret", "percentile_%ret"]

            detailed_top_assets_data = {}
            candles_to_report = {}
            if self.top is not None and not self.top.empty and (self.report_metrics or self.report_candles):
                i = 1
                for idx, row in self.top.iterrows():
                    base = row.get('base', '')

                    if self.report_metrics and not self.report_candles:
                        asset_data = {
                            "rank": int(i),
                            "base": str(base),
                            "price": self.candles[base].candles_df['close'].iloc[-1],
                        }

                        for key in report_keys:
                            asset_data[key] = self.all_metrics_df[key].get(base,0.0)

                    else:
                        try:
                            candles_w_indicators = self.get_indicators(self.candles[base], base, config=self.config,
                                                                   dbar=self.config.dbars)
                            indicators = candles_w_indicators.iloc[-1]
                        except:
                            candles_w_indicators = None
                            indicators = None
                        asset_data = {
                            "rank": int(indicators.get('rank', i)),
                            "base": str(indicators.get('base', '')),
                            "price": float(indicators.get('close', 0.0)),
                        }
                        for key in report_keys:
                            asset_data[key] = float(indicators.get(key, 0.0))

                        candles_to_report[
                            base] = candles_w_indicators.dropna().to_dict() if candles_w_indicators is not None else None

                    if self.report_metrics: detailed_top_assets_data[base] = asset_data
                    i += 1

            # Prepare bottom assets data
            bottom_assets_data = {
                "timestamp": pd.Timestamp.now().isoformat(),
                "type": "bottom_assets",
                "count": len(self.bottom),
                "assets": []
            }
            detailed_bottom_assets_data = {}

            if self.bottom is not None and not self.bottom.empty and (self.report_metrics or self.report_candles):
                i = 0
                for idx, row in self.bottom.iterrows():
                    base = row.get('base', '')
                    if self.report_metrics and not self.report_candles:
                        asset_data = {
                            "rank": int(i),
                            "base": str(base),
                            "price": self.candles[base].candles_df['close'].iloc[-1],
                        }

                        for key in report_keys:
                            asset_data[key] = self.all_metrics_df[key].get(base, 0.0)

                    else:
                        try:
                            candles_w_indicators = self.get_indicators(self.candles[base], base, config=self.config,
                                                                       dbar=self.config.dbars)
                            indicators = candles_w_indicators.iloc[-1]
                        except:
                            candles_w_indicators = None
                            indicators = None
                        asset_data = {
                            "rank": int(indicators.get('rank', i)),
                            "base": str(indicators.get('base', '')),
                            "price": float(indicators.get('close', 0.0)),
                        }
                        for key in report_keys:
                            asset_data[key] = float(indicators.get(key, 0.0))

                        candles_to_report[
                            base] = candles_w_indicators.dropna().to_dict() if candles_w_indicators is not None else None

                    if self.report_metrics: detailed_bottom_assets_data[base] = asset_data
                    i += 1

            # Publish to MQTT
            #if self.report_all_metrics:
            payload = {
                    "timestamp": pd.Timestamp.now().isoformat(),
                    "type": "combined_ranking",
                    "top_assets": self.top['base'].to_list(),
                    "bottom_assets": self.bottom['base'].to_list(),
                    "new_top": new_top if new_top else [],
                    "new_bottom": new_bottom if new_bottom else [],
                    "old_top": old_top if old_top else [],
                    "old_bottom": old_bottom if old_bottom else [],
                }
            if self.report_metrics:
                payload["detailed_top_assets"] = detailed_top_assets_data
                payload["detailed_bottom_assets"] = detailed_bottom_assets_data
            if self.report_candles:
                payload["candles"] = candles_to_report

            #topic = f"{self.config.mqtt_topic_prefix}"
            #publisher.publish(combined_topic, combined_data)
            #test_payload = {'test_key': 'test_value'}
            self.mqtt_pub.send(payload)
            # publisher.send(combined_data)
            self.logger().info(f"Published combined ranking to MQTT topic: {self.config.mqtt_topic_prefix}")

        except Exception as e:
            self.logger().error(f"Failed to publish MQTT ranking data: {str(e)}")

    async def update_processed_data(self):
        """
        Update the processed data based on the current state of the strategy.
        """
        # if candles are not started, create the candles dict and set the timer to 0 for each of them
        if not self.candles_started:
            self.logger().info("Initializing candles...")
            _ = len(self.config.candles_quote_asset)
            for key, candle in self.market_data_provider.candles_feeds.items():
                pair = key.split('_')[-2]
                key = f"{pair[:-_]}"
                self.candles[key] = candle
                # initialize the last timestamp to 0
                self.candles[key].last_timestamp = 0
            self.candles_started = True

        # if market analysis is not initialized call the function
        if not self.market_analysis_initialized:
            self.logger().info("Checking if candles are ready to start the market analysis")
            await self.initialize_market_analysis()

        else:
            await self.update_dbars()
            self.update_ranking()

        if self.raking_updated:
            self.raking_updated = False
            if not self.notifications: self.notifications = ""

            self.notifications += f"Top {self.config.n_pairs} pairs: \n {self.top[self.config.columns_to_report].to_string()} \n\n" \
                                  f"Bottom {self.config.n_pairs} pairs: \n {self.bottom[self.config.columns_to_report].to_string()}" \
                                  f"\n \n --------------------------------------------------------"
            #self.publish_mqtt_ranking()



    def report_candles_not_ready(self):
        """
        Report the candles that are not ready to be used for the market analysis
        """
        candles_not_ready = [trading_pair_interval for trading_pair_interval, candle in self.candles.items() if
                             not candle.dbar_ready]
        if len(candles_not_ready) > 0: self.logger().info(f"Candles NOT ready for analysis: {candles_not_ready}")

    async def initialize_market_analysis(self):
        if all(candle.dbar_ready for candle in self.candles.values()):
            self.logger().info("all candles are ready! ... initializing market analysis")
            self.all_metrics_df, self.market_status_metrics_df = self.create_market_analysis()

            current_top, current_bottom = self.get_ranking(self.all_metrics_df, self.config.sort_values_by,
                                                           self.config.n_pairs)

            self.top = current_top
            self.bottom = current_bottom
            self.raking_updated = True
            self.logger().info("Raking initialized!")
            self.publish_mqtt_ranking()

    def update_ranking(self):
        # update raking
        if self.metrics_updated:
            current_top, current_bottom = self.get_ranking(self.all_metrics_df, self.config.sort_values_by,
                                                           self.config.n_pairs)

            # check which asset have changed
            top_changed = self.top.index.difference(current_top.index)
            bottom_changed = self.bottom.index.difference(current_bottom.index)

            self.metrics_updated = False
            if len(top_changed) > 0 or len(bottom_changed) > 0:
                self.logger().info("Raking updated!")
                new_top_assets = [new_base for new_base in list(current_top.base) if
                                  new_base not in list(self.top.base)]
                old_top_assets = [old_base for old_base in list(self.top.base) if
                                  old_base not in list(current_top.base)]
                new_bottom_assets = [new_base for new_base in list(current_bottom.base) if
                                     new_base not in list(self.bottom.base)]
                old_bottom_assets = [old_base for old_base in list(self.bottom.base) if
                                     old_base not in list(current_bottom.base)]
                self.top = current_top
                self.bottom = current_bottom
                self.raking_updated = True
                # report top_changed and bottom_changed
                self.notifications = (
                    f"{len(new_top_assets) + len(new_bottom_assets)} have changed:\n Top {self.config.n_pairs}:\n" \
                    f"{old_top_assets} replaced by {new_top_assets}\n" \
                    f"Bottom {self.config.n_pairs}: \n" \
                    f"{old_bottom_assets} replaced by {new_bottom_assets}\n\n")

                # Publish to MQTT when ranking is updated
                self.publish_mqtt_ranking(new_top = new_top_assets, new_bottom=new_bottom_assets,
                                          old_top=old_top_assets, old_bottom=old_bottom_assets)

    async def update_dbars(self) -> None:
        for trading_pair_interval, candle in self.candles.items():
            # check if dbar_df is ready and if the last update is newer than the last time reported
            if candle.dbar_ready and candle.last_timestamp < candle.dbars_df["timestamp"].iloc[-1]:
                candle.last_timestamp = candle.dbars_df["timestamp"].iloc[-1]
                # get the indicators
                indicators_df = self.get_indicators(candle, trading_pair_interval, config=self.config,
                                                    dbar=self.config.dbars)

                # replace the values in the all_metrics_df for the trading pair
                self.all_metrics_df.loc[trading_pair_interval] = indicators_df.iloc[-1]
                self.logger().info(f"Updated metrics for {trading_pair_interval}")

                self.metrics_updated = True  # we set the flag to update the ranking

    #@staticmethod
    def get_ranking(self,all_metrics_df: pd.DataFrame, sort_values_by: List[str], n_side: int) -> tuple[
        DataFrame, DataFrame]:
        """
        Get the ranking of the trading pairs based on the metrics
        """
        all_metrics_df = all_metrics_df.sort_values(by=sort_values_by, ascending=False)

        # resorting the selected top and bottom by v fast
        top = all_metrics_df.head(n_side).sort_values(by='v', ascending=False)
        bottom = all_metrics_df.tail(n_side).sort_values(by='v', ascending=True)

        # filter out the ones with v_slow <= 0 from the top
        top = top[top['v2'] > 0]
        # filter out the ones with v_slow >= 0 from the bottom
        bottom = bottom[bottom['v2'] < 0]

        if self.config.filter_polarity:
            # filter out the ones with v <= 0 from the top
            top = top[top['v'] > 0]
            # filter out the ones with v >= 0 from the bottom
            bottom = bottom[bottom['v'] < 0]

        n_report_top = np.min([n_side, len(top)])
        # create a rank column for the top and bottom
        # if n_report_top only create the rank column
        if n_report_top > 0:
            top['rank'] = range(1, n_report_top + 1)
        else:
            top['rank'] = None
        n_report_bottom = np.min([n_side, len(bottom)])
        if n_report_bottom > 0:
            bottom['rank'] = range(1, n_report_bottom + 1)
        else:
            bottom['rank'] = None

        return top, bottom

    def get_processed_data(self) -> pd.DataFrame:
        if self.config.dbars:
            df = self.market_data_provider.get_dbar_df(
                self.config.candles_exchange,
                self.config.trading_pair,
                self.config.candles_interval,
                self.config.virtual_interval,
                self.config.n_records2dbars,
                self.max_records
            )
        else:
            df = self.market_data_provider.get_candles_df(
                self.config.candles_exchange,
                self.config.trading_pair,
                self.config.candles_interval,
                self.max_records
            )
        pass

    def create_market_analysis(self):
        market_metrics = {}
        market_satus_metrics = {}
        comparison_candle = self.candles['BTC']
        self.df_comparison = self.get_indicators(comparison_candle, 'BTC',
                                                 config=self.config, dbar=self.dbars)

        # we save the metrics for the usd pairs to report
        market_satus_metrics['BTC'] = self.df_comparison.iloc[-1]


        for trading_pair_interval, candle in self.candles.items():
            df = self.get_indicators(candle, trading_pair_interval, config=self.config, dbar=self.dbars)

            # we need to initialize the last timestamp
            candle.last_timestamp = df.iloc[-1]["timestamp"]

            market_metrics[trading_pair_interval] = df.iloc[-1]
            # if the pair is ETH-USDT we save the metrics to report
            if 'ETH' in trading_pair_interval:
                market_satus_metrics['ETH'] = df.iloc[-1]
        all_metrics_df = pd.DataFrame(market_metrics).T

        market_satus_metrics = pd.DataFrame(market_satus_metrics).T
        self.logger().info("Market analysis inizialized!")
        self.market_analysis_initialized = True
        return all_metrics_df, market_satus_metrics

    @staticmethod
    def get_indicators(candle, trading_pair_interval, config, dbar: bool = False):
        if dbar:
            df = candle.dbars_df.copy()
            df["interval"] = config.virtual_interval
        else:
            df = candle.candles_df.copy()
            df["interval"] = config.candles_interval
        df["base"] = trading_pair_interval

        # adding volatility metrics
        df["volatility"] = df["close"].pct_change().rolling(config.volatility_interval).std()
        df["volatility_pct"] = df["volatility"] / df["close"]
        df["volatility_pct_mean"] = df["volatility_pct"].rolling(config.volatility_interval).mean()

        # adding bbands metrics
        df.ta.bbands(length=config.volatility_interval, append=True)
        df["bbands_width_pct"] = df[f"BBB_{config.volatility_interval}_2.0"]
        df["bbands_width_pct_mean"] = df["bbands_width_pct"].rolling(config.volatility_interval).mean()
        df["bbands_percentage"] = df[f"BBP_{config.volatility_interval}_2.0"]
        df["natr"] = ta.natr(df["high"], df["low"], df["close"], length=config.volatility_interval)

        # adding Kalman filter
        if dbar:
            df = KF.kalman3_dollar(df, key='close', gain=config.kf_fast_gain, gain2=config.kf_slow_gain,
                                   gain3=config.kf_slower_gain)
        else:
            interval_in_s = candle.interval_to_seconds[df['interval']]
            df = KF.kalman3_tbars(df, interval_in_s, key='close', gain=config.kf_fast_gain, gain2=config.kf_slow_gain,
                                  gain3=config.kf_slower_gain)
        df['price_zscore'] = (df['close'] - df['x']) / df['close'].rolling(config.trend_interval).std()
        df['price_zscore2'] = (df['close'] - df['x2']) / df['close'].rolling(config.trend_interval).std()

        df['kf_delta'] = df['x'] - df['x2']

        df['a_zscore'] = (df['a'] - df['a'].rolling(config.trend_interval).mean()) / df['a'].rolling(
            config.trend_interval).std()
        df['v_zscore'] = (df['v'] - df['v'].rolling(config.trend_interval).mean()) / df['v'].rolling(
            config.trend_interval).std()
        # compute this for the second kalman filter
        df['a_zscore2'] = (df['a2'] - df['a2'].rolling(config.trend_interval).mean()) / df['a2'].rolling(
            config.trend_interval).std()
        df['v_zscore2'] = (df['v2'] - df['v2'].rolling(config.trend_interval).mean()) / df['v2'].rolling(
            config.trend_interval).std()

        # polarity of the trend True if both v and v2 are positive or negative
        df['trend_polarity'] = (df['v'] * df['v2']) > 0

        # adding pct change of the price
        df['price_%ret'] = df['close'].pct_change(config.pct_change_interval)
        df['percentile_%ret'] = [len(df[df['price_%ret'] <= df['price_%ret'].iloc[i]]) / (len(df) - 1) for i in
                                 range(len(df))]

        return df

    def determine_executor_actions(self) -> List[ExecutorAction]:
        """
        Determine actions based on the provided executor handler report.
        """
        actions = []
        return actions