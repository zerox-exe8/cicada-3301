from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

logger = logging.getLogger("kyro.tasks")

# Global strong-reference set to prevent garbage collection of running background tasks
_ACTIVE_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def create_tracked_task(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None,
) -> asyncio.Task[Any]:
    """
    Create an asyncio.Task while retaining a strong reference until execution completes.
    Prevents premature garbage collection of fire-and-forget background tasks.
    Logs unhandled exceptions automatically on task completion.
    """
    task = asyncio.create_task(coro, name=name)
    _ACTIVE_BACKGROUND_TASKS.add(task)

    def _on_done(t: asyncio.Task[Any]) -> None:
        _ACTIVE_BACKGROUND_TASKS.discard(t)
        if not t.cancelled():
            exc = t.exception()
            if exc:
                task_name = t.get_name() or name or "unnamed"
                logger.error(
                    f"Tracked background task '{task_name}' raised an unhandled exception: {exc}",
                    exc_info=exc,
                )

    task.add_done_callback(_on_done)
    return task


def get_active_task_count() -> int:
    """Return the count of currently executing tracked tasks."""
    return len(_ACTIVE_BACKGROUND_TASKS)
