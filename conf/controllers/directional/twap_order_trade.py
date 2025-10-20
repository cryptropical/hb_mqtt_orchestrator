import asyncio
import time
from enum import Enum
from decimal import Decimal
from typing import List, Dict, Any, Optional

from pydantic import Field

from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.remote_iface.mqtt import ExternalTopicFactory
from hummingbot.strategy_v2.controllers.directional_trading_controller_base import (
    DirectionalTradingControllerBase,
    DirectionalTradingControllerConfigBase,
)
from hummingbot.core.data_type.common import OrderType, TradeType, PositionAction, PriceType
from hummingbot.strategy_v2.executors.order_executor.data_types import ExecutionStrategy, OrderExecutorConfig
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, ExecutorAction
from hummingbot.strategy_v2.models.executors import CloseType


class ControllerState(Enum):
    """States for the TWAP Order Controller state machine"""
    IDLE = "idle"
    ENTERING = "entering"
    HOLDING = "holding"
    EXITING = "exiting"
    COMPLETED = "completed"
    ERROR = "error"


class TWAPOrderControllerConfig(DirectionalTradingControllerConfigBase):
    """Configuration for TWAP Order Controller using OrderExecutor"""
    
    controller_name: str = Field(default="twap_order_trade")
    controller_type: str = Field(default="directional_trading")

    # Trading parameters
    connector_name: str = Field(default="hyperliquid_perpetual")
    trading_pair: str = Field(default="XRP-USD")
    total_amount_quote: Decimal = Field(default=Decimal("1000"))
    entry_side: str = Field(default="BUY")  # BUY or SELL
    min_notional_size: Decimal = Field(default=Decimal("12"))  # Minimum notional size per order

    # TWAP parameters
    batch_size_quote: Decimal = Field(default=Decimal("100"))  # Size of each batch order
    batch_interval: int = Field(default=15)  # Time between batch orders in seconds
    execution_strategy: str = Field(default="LIMIT_MAKER")  # MARKET, LIMIT, LIMIT_MAKER, LIMIT_CHASER
    price_buffer_pct: Decimal = Field(default=Decimal("0.001"))  # 0.1% buffer for limit orders
    
    # Hold parameters
    hold_duration_seconds: int = Field(default=300)  # 5 minutes
    test_mode: bool = Field(default=True)  # If true, will auto-exit after hold duration
    
    # Risk management
    max_retries_per_batch: int = Field(default=3)  # Max retries for failed orders
    leverage: int = Field(default=1)  # For perpetual contracts
    position_mode: str = Field(default="ONEWAY")


    # topic for notifications
    notifications_topic: str = Field(default="hummmingbot/LS/notifications")


class TWAPOrderController(DirectionalTradingControllerBase):
    """
    TWAP Order Controller that implements Time-Weighted Average Price trading
    using multiple OrderExecutor instances to break large orders into smaller batches.
    
    This controller:
    1. Enters positions by placing multiple batch orders over time
    2. Holds the position for a specified duration (in test mode)
    3. Exits positions by placing multiple batch orders to close the position
    4. Handles failed orders with retry logic
    """

    def __init__(self, config: TWAPOrderControllerConfig, *args, **kwargs):
        """
        Initialize the TWAP Order Controller.
        
        Args:
            config: Configuration object containing trading parameters
        """
        super().__init__(config, *args, **kwargs)
        self._position_size = None
        self._stop_when_completed = True
        self._start_listener = True  # Whether to start the  signal listener
        self.config = config

        # State management
        self.state = ControllerState.IDLE
        self.entry_start_time: Optional[float] = None
        self.entry_completion_time: Optional[float] = None
        self.hold_start_time: Optional[float] = None
        self.exit_start_time: Optional[float] = None
        self.exit_completion_time: Optional[float] = None

        # TWAP batch tracking
        self.entry_batches_completed = 0
        self.entry_batches_total = 0
        self.exit_batches_completed = 0
        self.exit_batches_total = 0
        self.last_batch_time = 0
        
        # Position tracking
        self.entry_amount_filled = Decimal("0")
        #self.exit_amount_filled = Decimal("0")
        
        # Market data cache
        self._last_price = Decimal("0")

        # Trade sides
        self.entry_side = TradeType.BUY if config.entry_side.upper() == "BUY" else TradeType.SELL
        self.exit_side = TradeType.SELL if config.entry_side.upper() == "BUY" else TradeType.BUY

        # Control flags
        self._should_start_entry = True
        self._should_start_exit = False

        # Get connector and parse trading pair
        self.connector = self.market_data_provider.get_connector(self.config.connector_name)
        self.base = self.config.trading_pair.split("-")[0]
        self.quote = self.config.trading_pair.split("-")[1]

        # Calculate total batches needed for entry
        self.entry_batches_total = int(self.config.total_amount_quote / self.config.batch_size_quote)
        if self.config.total_amount_quote % self.config.batch_size_quote > 0:
            self.entry_batches_total += 1

        self.logger().info(f"TWAP Order Controller initialized for {self.config.trading_pair}")
        self.logger().info(f"Total entry batches planned: {self.entry_batches_total}")

        # Initialize notification system
        self.notifications = None

        # if the connector is in test mode start_entry here
        if self.config.test_mode:
            self.start_entry()
            self.logger().info("Test mode enabled, starting entry phase immediately")
        # auto-start entry phase if configured
        elif self._should_start_entry:
            self.start_entry()
            self.logger().info("Auto-starting entry phase based on configuration")

        if self._start_listener:
            self._init_signal_listener()

    def _init_signal_listener(self):
        """Initialize a listener for ML signals from the MQTT broker"""
        try:
            normalized_pair = self.config.trading_pair.replace("-", "_").lower()
            topic = f"{self.config.notifications_topic}/{normalized_pair}/control_signals"
            self._signal_listener = ExternalTopicFactory.create_async(
                topic=topic,
                callback=self._handle_signal,
                use_bot_prefix=False,
            )
            self.logger().info("ML signal listener initialized successfully")
        except Exception as e:
            self.logger().error(f"Failed to initialize ML signal listener: {str(e)}")
            self._signal_listener = None

    def _handle_signal(self, signal: dict, topic: str):
        """Handle incoming ML signal to control entry/exit phases"""
        # self.logger().info(f"Received ML signal: {signal}")
        if signal.get("action") == "start_entry":
            self.start_entry()
        elif signal.get("action") == "start_exit":
            self.logger().info("signal received, exiting phase starting")
            self._start_exit_phase() # start_exit()
        elif signal.get("action") == "new_total_quote":
            # TODO: This is not completed yet, we need to handle the new total quote and check the logic so the bot can continue trading
            new_total_quote = Decimal(signal.get("total_quote", "0"))
            if new_total_quote > self.config.total_amount_quote:
                self.config.total_amount_quote = new_total_quote
                self.entry_batches_total = int(new_total_quote / self.config.batch_size_quote)
                if new_total_quote % self.config.batch_size_quote > 0:
                    self.entry_batches_total += 1
                self.logger().info(f"Updated total amount quote to {new_total_quote}, "
                                  f"recalculated entry batches: {self.entry_batches_total}")

                if self.state == ControllerState.HOLDING:
                    # we need to change state to continue trading
                    self.state = ControllerState.ENTERING
        else:
            self.logger().warning(f"Unknown ML signal action: {signal.get('action')}")


    @property
    def is_perpetual(self) -> bool:
        """Check if trading perpetual contracts"""
        return "perpetual" in self.config.connector_name.lower()

    @property
    def position_size(self) -> Decimal:
        """Get current position size in base currency"""
        try:
            return self.get_position_size()
        except Exception as e:
            self.logger().error(f"Error getting position size: {e}")
            return Decimal("0")

    def get_position_size(self):
        try:
            if self.state == ControllerState.ENTERING or self.state == ControllerState.HOLDING:
                filled_dict = self.connector.order_filled_balances()
                self._position_size = abs(filled_dict.get(self.base, Decimal("0")))
                position_size = self._position_size
            elif self.state == ControllerState.IDLE:
                # In IDLE state, we assume no position is held
                position_size = 0
            else:
                position_size = self._position_size
            return position_size
        except Exception as e:
            self.logger().error(f"Error getting position size: {e}")
            return Decimal("0")

    @property
    def entry_avg_price(self) -> Decimal:
        """Calculate average entry price from filled orders"""
        try:
            filled_dict = self.connector.order_filled_balances()
            filled_quote = abs(filled_dict.get(self.quote, Decimal("0")))
            filled_base = abs(filled_dict.get(self.base, Decimal("0")))
            
            if filled_base > 0:
                return filled_quote / filled_base
            return Decimal("0")
        except Exception as e:
            self.logger().error(f"Error calculating entry avg price: {e}")
            return Decimal("0")

    @property
    def exit_amount_filled(self) -> Decimal:
        """Get total amount filled for exit orders"""
        try:
            completed_exit_executors = self.filter_executors(
                executors=self.executors_info,
                filter_func=lambda x: (x.is_done and
                                       hasattr(x, 'custom_info') and
                                       x.custom_info.get('level_id', '').startswith('exit_batch_'))
            )
            total_exit_amount = Decimal("0")
            for executor in completed_exit_executors:
                if hasattr(executor, 'filled_amount_base'):
                    total_exit_amount += executor.filled_amount_base
            return total_exit_amount
        except Exception as e:
            self.logger().error(f"Error getting exit amount filled: {e}")
            return Decimal("0")

    async def update_processed_data(self):
        """
        Main controller logic called periodically by the framework.
        Implements the state machine for TWAP trading.
        """
        try:
            # Update current market price
            self._update_current_price()

            # State machine logic
            if self.state == ControllerState.IDLE and self._should_start_entry:
                self._start_entry_phase()
                
            elif self.state == ControllerState.ENTERING:
                self._monitor_entry_progress()
                
            elif self.state == ControllerState.HOLDING:
                self._check_exit_conditions()
                
            elif self.state == ControllerState.EXITING:
                self._monitor_exit_progress()
                
            elif self.state == ControllerState.COMPLETED:
                self._report_final_results()
                # close hummingbot gracefully



        except Exception as e:
            self.logger().error(f"Error in update_processed_data: {e}")
            self._handle_error(str(e))

    def _update_current_price(self, price_type: PriceType = PriceType.MidPrice):
        """Update current market price for calculations"""
        try:
            price = self.market_data_provider.get_price_by_type(
                self.config.connector_name,
                self.config.trading_pair,
                price_type
            )
            if price and price > 0:
                self._last_price = price
        except Exception as e:
            self.logger().error(f"Error updating current price: {e}")

    def determine_executor_actions(self) -> List[ExecutorAction]:
        """
        Create executor actions based on current state and timing.
        This method is called by the framework to get new orders to place.
        """
        actions = []
        current_time = self.market_data_provider.time()

        try:
            # Check if it's time for the next batch and we're in the right state
            if (current_time - self.last_batch_time >= self.config.batch_interval or
                    self.last_batch_time == 0):

                if self.state == ControllerState.ENTERING:
                    # Check if there are any active entry executors before creating new ones
                    active_entry_executors = self.filter_executors(
                        executors=self.executors_info,
                        filter_func=lambda x: (x.is_active and
                                               hasattr(x, 'custom_info') and
                                               x.custom_info.get('level_id', '').startswith('entry_batch_'))
                    )

                    # Only create new batch if no active entry executors exist
                    if len(active_entry_executors) == 0:
                        action = self._create_entry_batch_action()
                        if action:
                            actions.append(action)
                            self.last_batch_time = current_time
                    else:
                        self.logger().debug(
                            f"Skipping new entry batch - {len(active_entry_executors)} active executor(s) still processing")

                elif self.state == ControllerState.EXITING:
                    # Check if there are any active exit executors before creating new ones
                    active_exit_executors = self.filter_executors(
                        executors=self.executors_info,
                        filter_func=lambda x: (x.is_active and
                                               hasattr(x, 'custom_info') and
                                               x.custom_info.get('level_id', '').startswith('exit_batch_'))
                    )

                    # Only create new batch if no active exit executors exist
                    if len(active_exit_executors) == 0:
                        action = self._create_exit_batch_action()
                        if action:
                            actions.append(action)
                            self.last_batch_time = current_time
                    else:
                        self.logger().debug(
                            f"Skipping new exit batch - {len(active_exit_executors)} active executor(s) still processing")

        except Exception as e:
            self.logger().error(f"Error creating executor actions: {e}")

        return actions

    def _create_entry_batch_action(self) -> Optional[CreateExecutorAction]:
        """
        Create an order executor action for the next entry batch.
        
        Returns:
            CreateExecutorAction or None if no more batches needed
        """
        #if self.entry_batches_completed >= self.entry_batches_total:
        #    return None
            
        # Calculate batch size (handle last batch which might be smaller)
        remaining_quote = self.config.total_amount_quote - self.entry_amount_filled
        # here we control that the remaining quote after this trade is greater than the minimum notional size
        if remaining_quote <= self.config.min_notional_size:
            self.logger().warning("Remaining quote is less than minimum notional size, cannot place more orders.")
            return None
        batch_quote = min(self.config.batch_size_quote, remaining_quote)
        # then we need to check if the remaining quote after this trade is sufficient to place a batch order otherwise we increase the batch size
        if (remaining_quote - batch_quote) < self.config.min_notional_size:
            batch_quote = remaining_quote
            self.entry_batches_total -= 1  # Adjust total batches since this is the last one
            self.entry_batches_total = max(self.entry_batches_total, 1)  # Ensure total is not less than 1
            self.logger().info(f"Adjusting entry batches total to {self.entry_batches_total} due to last batch size")

        
        if batch_quote <= Decimal("0"):
            return None
            
        # Convert quote amount to base amount
        batch_amount = batch_quote / self._last_price
        
        # Create order executor config
        order_config = OrderExecutorConfig(
            timestamp=self.market_data_provider.time(),
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            side=self.entry_side,
            amount=batch_amount,
            execution_strategy=self._get_execution_strategy(),
            price=self._get_order_price(self.entry_side),
            position_action=PositionAction.OPEN,
            leverage=self.config.leverage if self.is_perpetual else 1,
            level_id=f"entry_batch_{self.entry_batches_completed + 1}"
        )
        
        self.logger().info(f"Creating entry batch {self.entry_batches_completed + 1}/{self.entry_batches_total} "
                          f"for {batch_quote} quote ({batch_amount} base)")
        
        return CreateExecutorAction(
            controller_id=self.config.id,
            executor_config=order_config
        )

    def _create_exit_batch_action(self) -> Optional[CreateExecutorAction]:
        """
        Create an order executor action for the next exit batch.
        
        Returns:
            CreateExecutorAction or None if no more batches needed
        """
        #if self.exit_batches_completed >= self.exit_batches_total:
        #    return None
            
        # Calculate remaining position to exit
        self._update_exit_fill_tracking()
        remaining_position =  self.position_size - self.exit_base_amount_filled
        if remaining_position <= Decimal("0"):
            return None

        remaining_position_quote = remaining_position * self._last_price

        # get the btch size based on the current price
        if remaining_position_quote <= self.config.min_notional_size:
            self.logger().warning("Remaining position is less than minimum notional size, cannot place more orders.")
            return None
        # Calculate batch size (handle last batch which might be smaller)
        batch_size_quote = min(self.config.batch_size_quote, remaining_position_quote)
        # here we control that the remaining position after this trade is greater than the minimum notional size
        if (remaining_position_quote - batch_size_quote) < self.config.min_notional_size:
            batch_size_quote = remaining_position_quote
            self.exit_batches_total-= 1  # Adjust total batches since this is the last one
            self.logger().info(f"Adjusting exit batches total to {self.exit_batches_total} due to last batch size")

        if batch_size_quote <= Decimal("0"):
            return None
        # Convert quote amount to base amount
        batch_size_base = batch_size_quote / self._last_price

        ## Calculate batch size for exit
        #batch_size_base = min(
        #    self.config.batch_size_quote / self._last_price,  # Convert batch size to base
        #    remaining_position
        #)
        ## Ensure the remaining position after this trade is greater than the minimum notional size
        #if (remaining_position - batch_size_base) * self._last_price < self.config.min_notional_size:
        #    self.logger().warning("Remaining position after this trade is less than minimum notional size, resizing batch.")
        #    batch_size_base = self.position_size - self.exit_base_amount_filled


        
        # Create order executor config
        order_config = OrderExecutorConfig(
            timestamp=self.market_data_provider.time(),
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            side=self.exit_side,
            amount=batch_size_base,
            execution_strategy=self._get_execution_strategy(),
            price=self._get_order_price(self.exit_side),
            position_action=PositionAction.CLOSE,
            leverage=self.config.leverage if self.is_perpetual else 1,
            level_id=f"exit_batch_{self.exit_batches_completed + 1}"
        )
        
        self.logger().info(f"Creating exit batch {self.exit_batches_completed + 1}/{self.exit_batches_total} "
                          f"for {batch_size_base} base")
        
        return CreateExecutorAction(
            controller_id=self.config.id,
            executor_config=order_config
        )

    def _get_execution_strategy(self) -> ExecutionStrategy:
        """Convert string execution strategy to enum"""
        strategy_map = {
            "MARKET": ExecutionStrategy.MARKET,
            "LIMIT": ExecutionStrategy.LIMIT,
            "LIMIT_MAKER": ExecutionStrategy.LIMIT_MAKER,
            "LIMIT_CHASER": ExecutionStrategy.LIMIT_CHASER
        }
        return strategy_map.get(self.config.execution_strategy.upper(), ExecutionStrategy.LIMIT_MAKER)

    def _get_order_price(self, side: TradeType) -> Optional[Decimal]:
        """
        Calculate order price based on execution strategy and side.
        
        Args:
            side: Order side (BUY or SELL)
            
        Returns:
            Price for the order or None for market orders
        """
        if self._get_execution_strategy() == ExecutionStrategy.MARKET:
            return self._last_price
            
        # For limit orders, apply a small buffer to improve fill probability
        if side == TradeType.BUY:
            # For buy orders, place slightly above market price
            return self._last_price * (Decimal("1") + self.config.price_buffer_pct)
        else:
            # For sell orders, place slightly below market price
            return self._last_price * (Decimal("1") - self.config.price_buffer_pct)

    def _start_entry_phase(self):
        """Initialize the entry phase of TWAP trading"""
        self.state = ControllerState.ENTERING
        self.entry_start_time = time.time()
        self._should_start_entry = False
        self.last_batch_time = 0  # Reset to allow immediate first batch
        
        self.logger().info(f"Starting TWAP entry for {self.config.total_amount_quote} quote "
                          f"in {self.entry_batches_total} batches")

    def _monitor_entry_progress(self):
        """Monitor progress of entry batches and transition to holding when complete"""
        # Check for failed executors that exhausted retries
        failed_entry_executors = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (x.is_done and not x.close_type == CloseType.POSITION_HOLD and
                                   hasattr(x, 'custom_info') and
                                   x.custom_info.get('level_id', '').startswith('entry_batch_'))
        )

        if len(failed_entry_executors) > 0:
            self.logger().warning(f"Found {len(failed_entry_executors)} failed entry executor(s)")
            # Handle failed executors - maybe adjust totals or trigger error state

        # Count completed entry executors
        completed_entry_executors = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (x.is_done and x.close_type == CloseType.POSITION_HOLD and
                                 hasattr(x, 'custom_info') and 
                                 x.custom_info.get('level_id', '').startswith('entry_batch_'))
        )
        
        self.entry_batches_completed = len(completed_entry_executors)
        
        # Update filled amount tracking
        self._update_entry_fill_tracking()
        
        # Check if entry phase is complete based on the filled amount
        if self.entry_amount_filled >= (self.config.total_amount_quote - self.config.min_notional_size):
            # Ensure we don't count more batches than planned
            if self.entry_batches_completed > self.entry_batches_total:
                self.logger().warning("Entry batches completed exceeds total planned batches, adjusting.")
                self.entry_batches_total = self.entry_batches_completed

            self._complete_entry_phase()

    def _complete_entry_phase(self):
        """Transition from entry to holding phase"""
        self.state = ControllerState.HOLDING
        self.entry_completion_time = time.time()
        self.hold_start_time = time.time()
        
        entry_duration = self.entry_completion_time - self.entry_start_time
        self.logger().info(f"Entry phase completed in {entry_duration:.1f}s. "
                          f"Position: {self.position_size}, Avg Price: {self.entry_avg_price:.2f}, {(self.entry_avg_price* self.position_size):.2f} {self.quote} filled")

    def _check_exit_conditions(self):
        """Check if conditions are met to start exit phase"""
        if self.config.test_mode and self.hold_start_time:
            elapsed_time = time.time() - self.hold_start_time
            if elapsed_time >= self.config.hold_duration_seconds:
                self._start_exit_phase()
        elif self._should_start_exit:
            self._start_exit_phase()

    def _start_exit_phase(self):
        """Initialize the exit phase of TWAP trading"""
        current_position = self.position_size
        if current_position <= Decimal("0"):
            self.logger().warning("No position to exit")
            self.state = ControllerState.COMPLETED
            return
            
        self.state = ControllerState.EXITING
        self.exit_start_time = time.time()
        self._should_start_exit = False
        self.last_batch_time = 0  # Reset to allow immediate first batch
        
        # Calculate exit batches based on current position
        position_value = current_position * self._last_price
        self.exit_batches_total = int(position_value / self.config.batch_size_quote)
        if position_value % self.config.batch_size_quote > 0:
            self.exit_batches_total += 1
            
        self.logger().info(f"Starting TWAP exit for position {current_position} "
                          f"in {self.exit_batches_total} batches")

    def _monitor_exit_progress(self):
        """Monitor progress of exit batches and transition to completed when done"""
        # Count completed exit executors
        completed_exit_executors = self.filter_executors(
            executors=self.executors_info,
            filter_func=lambda x: (x.is_done and 
                                 hasattr(x, 'custom_info') and 
                                 x.custom_info.get('level_id', '').startswith('exit_batch_'))
        )
        
        self.exit_batches_completed = len(completed_exit_executors)
        
        # Update filled amount tracking
        self._update_exit_fill_tracking()
        
        # Check if exit phase is complete
        if self.exit_base_amount_filled >= self.position_size:
            self._complete_exit_phase()
            if self.holding_amount > 0:
                self.logger().warning(f"Exit phase completed with remaining position: {self.holding_amount} {self.base}")
        # TODO: Add logic to handle partial exits if needed

    def _complete_exit_phase(self):
        """Complete the exit phase and transition to completed state"""
        self.state = ControllerState.COMPLETED
        self.exit_completion_time = time.time()
        
        exit_duration = self.exit_completion_time - self.exit_start_time
        self.logger().info(f"Exit phase completed in {exit_duration:.1f}s. "
                          f"Remaining position: {self.position_size}")
        if self._stop_when_completed:
            self._report_final_results()
            self.logger().info("TWAP Order Controller completed all operations, stopping.")
            # Stop the controller gracefully
            HummingbotApplication.main_application().stop()

    def _update_entry_fill_tracking(self):
        """Update tracking of filled entry amounts"""
        try:
            filled_dict = self.connector.order_filled_balances()
            self.entry_amount_filled = abs(filled_dict.get(self.quote, Decimal("0")))
        except Exception as e:
            self.logger().error(f"Error updating entry fill tracking: {e}")

    def _update_exit_fill_tracking(self):
        """Update tracking of filled exit amounts"""
        try:
            # For exit tracking, we need to track how much of the position has been closed
            # This is complex with the current approach, so we'll use a simplified method
            # completed_exit_executors = self.filter_executors(
            #    executors=self.executors_info,
            #    filter_func=lambda x: (x.is_done and
            #                         hasattr(x, 'custom_info') and
            #                         x.custom_info.get('level_id', '').startswith('exit_batch_'))
            #)
            
            #total_exit_amount = Decimal("0")
            #for executor in completed_exit_executors:
            #    if hasattr(executor, 'filled_amount_base'):
            #        total_exit_amount += executor.filled_amount_base

            filled_dict = self.connector.order_filled_balances()
            self.holding_amount = abs(filled_dict.get(self.base, Decimal("0")))
            self.exit_base_amount_filled = self.position_size - self.holding_amount
            
        except Exception as e:
            self.logger().error(f"Error updating exit fill tracking: {e}")

    #async def on_stop(self):
    #    self.start_exit()
    #    while self.state != ControllerState.COMPLETED:
    #        await asyncio.sleep(1.0)



    def _handle_error(self, error_msg: str):
        """Handle errors and transition to error state"""
        self.state = ControllerState.ERROR
        self.logger().error(f"TWAP Controller Error: {error_msg}")

    def _report_final_results(self):
        """Report final trading results (called once when completed)"""
        if not hasattr(self, '_results_reported'):
            total_duration = self.exit_completion_time - self.entry_start_time
            self.logger().info("=== TWAP Trading Completed ===")
            self.logger().info(f"Total Duration: {total_duration:.1f}s")
            self.logger().info(f"Entry Batches: {self.entry_batches_completed}/{self.entry_batches_total}")
            self.logger().info(f"Exit Batches: {self.exit_batches_completed}/{self.exit_batches_total}")
            self.logger().info(f"Final Position: {self.position_size}")
            self._results_reported = True

    # Public control methods
    def start_entry(self):
        """Public method to trigger entry phase"""
        if self.state == ControllerState.IDLE:
            self._should_start_entry = True
            self.logger().info("Entry start requested")
        else:
            self.logger().warning(f"Cannot start entry from state: {self.state}")

    def start_exit(self):
        """Public method to trigger exit phase"""
        # TODO: we might want to allow exit from holding and entering states this doesnt work properly yet
        # need to change it in the signal handler too
        if self.state == ControllerState.HOLDING:
            self._should_start_exit = True
            self.logger().info("Exit start requested")
        else:
            self.logger().warning(f"Cannot start exit from state: {self.state}")

    def update_strategy_markets_dict(self, markets_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update markets dict for strategy"""
        if self.config.connector_name not in markets_dict:
            markets_dict[self.config.connector_name] = [self.config.trading_pair]
        else:
            if self.config.trading_pair not in markets_dict[self.config.connector_name]:
                markets_dict[self.config.connector_name].append(self.config.trading_pair)
        return markets_dict

    def to_format_status(self) -> List[str]:
        """Format status information for display"""
        lines = []
        lines.append(f"Controller: {self.config.controller_name}")
        lines.append(f"State: {self.state.value}")
        lines.append(f"Trading Pair: {self.config.trading_pair}")
        lines.append(f"Total Amount: {self.config.total_amount_quote} quote")
        lines.append(f"Batch Size: {self.config.batch_size_quote} quote")
        lines.append(f"Batch Interval: {self.config.batch_interval}s")
        lines.append(f"Position Size: {self.position_size}")
        lines.append(f"Entry Avg Price: {self.entry_avg_price}")
        lines.append(f"Current Price: {self._last_price}")

        # Progress information
        if self.state == ControllerState.ENTERING:
            lines.append(f"Entry Progress: {self.entry_batches_completed}/{self.entry_batches_total}")
            if self.entry_start_time:
                elapsed = time.time() - self.entry_start_time
                lines.append(f"Entry Duration: {elapsed:.1f}s")
                
        elif self.state == ControllerState.HOLDING:
            if self.hold_start_time:
                hold_elapsed = time.time() - self.hold_start_time
                hold_remaining = max(0, self.config.hold_duration_seconds - hold_elapsed)
                lines.append(f"Hold Remaining: {hold_remaining:.1f}s")
                
        elif self.state == ControllerState.EXITING:
            lines.append(f"Exit Progress: {self.exit_batches_completed}/{self.exit_batches_total}")
            if self.exit_start_time:
                elapsed = time.time() - self.exit_start_time
                lines.append(f"Exit Duration: {elapsed:.1f}s")

        # Active executors
        active_executors = len([e for e in self.executors_info if e.is_active])
        lines.append(f"Active Orders: {active_executors}")

        return lines

    def get_controller_status(self) -> Dict[str, Any]:
        """Get detailed controller status as dictionary"""
        return {
            "controller_name": self.config.controller_name,
            "state": self.state.value,
            "trading_pair": self.config.trading_pair,
            "total_amount_quote": float(self.config.total_amount_quote),
            "batch_size_quote": float(self.config.batch_size_quote),
            "position_size": float(self.position_size),
            "entry_avg_price": float(self.entry_avg_price),
            "current_price": float(self._last_price),
            "entry_batches_completed": self.entry_batches_completed,
            "entry_batches_total": self.entry_batches_total,
            "exit_batches_completed": self.exit_batches_completed,
            "exit_batches_total": self.exit_batches_total,
            "entry_amount_filled": float(self.entry_amount_filled),
            "exit_amount_filled": float(self.exit_amount_filled),
        }
