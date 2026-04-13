"""
Async broadcast event bus for agent activity SSE events.

Design constraints:
- agent_service.run() is synchronous (runs in uvicorn's thread pool executor).
- The SSE endpoint is async and lives in the event loop.
- publish() bridges the two using loop.call_soon_threadsafe() so sync callers
  can safely enqueue events into async subscriber queues.

Usage:
  Startup (main.py lifespan):
      from services.event_bus import set_main_loop
      set_main_loop(asyncio.get_running_loop())

  Sync callers (agent_service.py):
      from services.event_bus import publish
      publish({"type": "agent_start", "agent_name": agent_name, ...})

  Async SSE endpoint (routers/agent.py):
      from services.event_bus import subscribe, unsubscribe
      q = subscribe()
      try:
          event = await asyncio.wait_for(q.get(), timeout=25.0)
      finally:
          unsubscribe(q)
"""
import asyncio
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("deckr.event_bus")

_lock: threading.Lock = threading.Lock()
_subscribers: list[asyncio.Queue] = []
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Call once at application startup from the async lifespan context."""
    global _main_loop
    _main_loop = loop
    logger.info("event_bus: main loop registered")


def subscribe(maxsize: int = 100) -> asyncio.Queue:
    """Create and register a new subscriber queue. Called from async context."""
    q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    with _lock:
        _subscribers.append(q)
    logger.debug("event_bus: subscriber added (total=%d)", len(_subscribers))
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a subscriber queue. Called when the SSE client disconnects."""
    with _lock:
        try:
            _subscribers.remove(q)
            logger.debug("event_bus: subscriber removed (total=%d)", len(_subscribers))
        except ValueError:
            pass


def publish(event: dict) -> None:
    """
    Thread-safe broadcast to all SSE subscribers.

    Safe to call from synchronous (thread-pool) context. Silently no-ops if
    no loop has been registered or no subscribers are connected.
    """
    loop = _main_loop
    if loop is None or not loop.is_running():
        return

    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    with _lock:
        subs = list(_subscribers)

    if not subs:
        return

    for q in subs:
        try:
            loop.call_soon_threadsafe(q.put_nowait, event)
        except asyncio.QueueFull:
            logger.warning("event_bus: subscriber queue full — dropping event type=%s", event.get("type"))
        except Exception as exc:
            logger.warning("event_bus: failed to enqueue event — %s", exc)
