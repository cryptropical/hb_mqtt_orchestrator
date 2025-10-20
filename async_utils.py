"""
Async utilities for handling cross-thread async operations
"""

import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)


def schedule_async_task(coro: Coroutine, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """
    Schedule an async coroutine as a task from any thread.
    
    Args:
        coro: The coroutine to schedule
        loop: The event loop to use (if None, tries to get the running loop)
    """
    try:
        if loop is None:
            # Try to get the running loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, try to get the event loop
                loop = asyncio.get_event_loop()
        
        # Check if we're in the same thread as the loop
        try:
            # If we can get the running loop, we're in the async context
            current_loop = asyncio.get_running_loop()
            if current_loop == loop:
                # We're in the loop's thread, create task directly
                loop.create_task(coro)
            else:
                # Different loop, use thread-safe scheduling
                asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            # We're not in an async context, use thread-safe scheduling
            def create_task():
                task = loop.create_task(coro)
                task.add_done_callback(_handle_task_exception)
            
            loop.call_soon_threadsafe(create_task)
            
    except Exception as e:
        logger.error(f"Error scheduling async task: {e}", exc_info=True)


def _handle_task_exception(task: asyncio.Task) -> None:
    """Handle exceptions from scheduled tasks"""
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task was cancelled, this is normal
    except Exception as e:
        logger.error(f"Exception in scheduled task: {e}", exc_info=True)


async def run_in_task(coro: Coroutine) -> Any:
    """
    Ensure a coroutine runs in a proper task context.
    
    This is useful when you need to ensure aiohttp operations
    run within a task context.
    """
    return await asyncio.create_task(coro)