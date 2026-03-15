"""Common helpers used across the package."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
CommandPrefix = tuple[str, ...]
SAFE_COMMAND_PREFIXES: CommandPrefix = ("/",)
logger = logging.getLogger("telebridge")


@dataclass(slots=True)
class ParsedCommand:
    """Normalized command data extracted from an incoming message."""

    name: str
    args: list[str]
    raw: str


def normalize_command_prefixes(
    prefixes: Any,
    *,
    default: CommandPrefix = SAFE_COMMAND_PREFIXES,
) -> CommandPrefix:
    """Normalize command prefixes to a safe tuple of strings."""

    if prefixes is None:
        return default

    if not isinstance(prefixes, (list, tuple, set)):
        logger.warning("Invalid prefix configuration detected; using default '/'")
        return default

    normalized = tuple(str(prefix).strip() for prefix in prefixes if str(prefix).strip())
    if not normalized:
        logger.warning("Invalid prefix configuration detected; using default '/'")
        return default

    return normalized


def parse_command(text: str | None, prefixes: Any = ("/", ".", "!")) -> ParsedCommand | None:
    """Parse Telegram-style commands from text."""

    if not text:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    prefixes = normalize_command_prefixes(prefixes)
    token, *rest = stripped.split()
    matched_prefix = next((prefix for prefix in prefixes if token.startswith(prefix)), None)
    if matched_prefix is None:
        return None

    command = token[len(matched_prefix) :]
    if "@" in command:
        command = command.split("@", maxsplit=1)[0]

    if not command:
        return None

    parsed = ParsedCommand(name=command.lower(), args=rest, raw=stripped)
    logger.debug("Parsed command: %s", parsed.name)
    logger.debug("Prefix used: %s", matched_prefix)
    return parsed


def format_message(template: str, **values: Any) -> str:
    """Safely format user-facing strings."""

    return template.format(**values)


def error_boundary(
    logger: Any,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T | None]]]:
    """Wrap async callables so handler failures are logged consistently."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T | None]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Runtime error in handler '%s': %s", func.__name__, exc)
                return None

        return wrapper

    return decorator


class RateLimiter:
    """Simple in-memory async rate limiter keyed by arbitrary strings."""

    def __init__(self, period: float = 1.0) -> None:
        self.period = period
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> bool:
        """Return True if the key may proceed now, otherwise False."""

        async with self._lock:
            now = time.monotonic()
            previous = self._seen.get(key)
            if previous is not None and now - previous < self.period:
                return False

            self._seen[key] = now
            return True


class SlidingWindowRateLimiter:
    """Wait until a global request budget has capacity."""

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait_for_slot(self) -> float:
        """Block until a request slot is available and return the wait time."""

        waited = 0.0
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._events and now - self._events[0] >= self.period:
                    self._events.popleft()

                if len(self._events) < self.max_calls:
                    self._events.append(now)
                    return waited

                delay = max(0.0, self.period - (now - self._events[0]))

            if delay > 0:
                waited += delay
                await asyncio.sleep(delay)


class DuplicateMessageTracker:
    """Track repeated outbound payloads and recommend a cooldown."""

    def __init__(self, limit: int = 3, period: float = 60.0) -> None:
        self.limit = limit
        self.period = period
        self._messages: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def extra_delay(self, key: str | None) -> float:
        """Return an extra delay when the same payload repeats too often."""

        if not key or self.limit <= 0:
            return 0.0

        async with self._lock:
            now = time.monotonic()
            seen = self._messages.setdefault(key, deque())
            while seen and now - seen[0] >= self.period:
                seen.popleft()

            delay = 0.0
            if len(seen) >= self.limit - 1:
                delay = float(min(5, len(seen) - self.limit + 2))

            seen.append(now)
            return delay
