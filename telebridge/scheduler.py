"""Background task scheduler."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

TaskCallback = Callable[[], Awaitable[Any]]


@dataclass(slots=True)
class ScheduledTask:
    """Metadata about a repeating background task."""

    interval: float
    callback: TaskCallback
    run_on_start: bool = False


class Scheduler:
    """Run periodic async tasks for the application."""

    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.tasks: list[ScheduledTask] = []
        self._running: list[asyncio.Task[Any]] = []
        self._stop_event = asyncio.Event()

    def task(self, *, interval: float, run_on_start: bool = False) -> Callable[[TaskCallback], TaskCallback]:
        if interval <= 0:
            raise ValueError("Task interval must be greater than zero")

        def decorator(func: TaskCallback) -> TaskCallback:
            self.tasks.append(ScheduledTask(interval=interval, callback=func, run_on_start=run_on_start))
            self.logger.debug("Background task registered: %s", func.__name__)
            return func

        return decorator

    async def start(self) -> None:
        self._stop_event = asyncio.Event()
        for task in self.tasks:
            if task.run_on_start:
                await self._execute(task)
            self._running.append(asyncio.create_task(self._runner(task)))

    async def _runner(self, task: ScheduledTask) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=task.interval)
            except asyncio.TimeoutError:
                await self._execute(task)

    async def _execute(self, task: ScheduledTask) -> None:
        try:
            await task.callback()
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.exception("Runtime error in background task '%s': %s", task.callback.__name__, exc)

    async def stop(self) -> None:
        self._stop_event.set()
        for running in self._running:
            running.cancel()
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)
        self._running.clear()
