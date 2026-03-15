"""Routing primitives for commands, buttons, inline queries, and middleware."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from telebridge.filters import FILTER_ATTR, HANDLER_ATTR, FilterSpec
from telebridge.utils import ParsedCommand, error_boundary

HandlerCallback = Callable[[Any], Awaitable[Any]]
MiddlewareCallback = Callable[[Any, Callable[[], Awaitable[Any]]], Awaitable[Any]]


@dataclass(slots=True)
class BaseHandler:
    """A registered callback plus routing metadata."""

    callback: HandlerCallback
    filters: list[FilterSpec] = field(default_factory=list)
    owner_only: bool = False


@dataclass(slots=True)
class CommandHandler(BaseHandler):
    commands: tuple[str, ...] = ()

    def matches(self, parsed: ParsedCommand | None) -> bool:
        return parsed is not None and parsed.name in self.commands


@dataclass(slots=True)
class ButtonHandler(BaseHandler):
    patterns: tuple[str, ...] = ()

    def matches(self, callback_data: str | None) -> bool:
        return callback_data is not None and callback_data in self.patterns


@dataclass(slots=True)
class InlineHandler(BaseHandler):
    def matches(self, _: Any = None) -> bool:
        return True


class Router:
    """Register and dispatch command handlers, button handlers, and inline handlers."""

    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.handlers: list[CommandHandler] = []
        self.button_handlers: list[ButtonHandler] = []
        self.inline_handlers: list[InlineHandler] = []
        self.middlewares: list[MiddlewareCallback] = []

    def command(
        self,
        *items: str | FilterSpec,
        owner: bool = False,
    ) -> Callable[[HandlerCallback], HandlerCallback]:
        names, extra_filters = self._split_items(items)
        normalized = tuple(name.lower() for name in names if name)
        if not normalized:
            raise ValueError("At least one command name is required")

        def decorator(func: HandlerCallback) -> HandlerCallback:
            handler = CommandHandler(
                commands=normalized,
                callback=error_boundary(self.logger)(func),
                filters=self._collect_filters(func, extra_filters),
                owner_only=owner,
            )
            self.handlers.append(handler)
            self._track_handler(func, handler)

            for name in normalized:
                self.logger.debug("Command registered: %s", name)
            return func

        return decorator

    def button(
        self,
        *items: str | FilterSpec,
        owner: bool = False,
    ) -> Callable[[HandlerCallback], HandlerCallback]:
        names, extra_filters = self._split_items(items)
        normalized = tuple(name for name in names if name)
        if not normalized:
            raise ValueError("At least one callback data value is required")

        def decorator(func: HandlerCallback) -> HandlerCallback:
            handler = ButtonHandler(
                patterns=normalized,
                callback=error_boundary(self.logger)(func),
                filters=self._collect_filters(func, extra_filters),
                owner_only=owner,
            )
            self.button_handlers.append(handler)
            self._track_handler(func, handler)

            for name in normalized:
                self.logger.debug("Button handler registered: %s", name)
            return func

        return decorator

    def inline(
        self,
        *filters: FilterSpec,
        owner: bool = False,
    ) -> Callable[[HandlerCallback], HandlerCallback]:
        def decorator(func: HandlerCallback) -> HandlerCallback:
            handler = InlineHandler(
                callback=error_boundary(self.logger)(func),
                filters=self._collect_filters(func, list(filters)),
                owner_only=owner,
            )
            self.inline_handlers.append(handler)
            self._track_handler(func, handler)
            self.logger.debug("Inline handler registered: %s", func.__name__)
            return func

        return decorator

    def middleware(self, func: MiddlewareCallback) -> MiddlewareCallback:
        self.middlewares.append(func)
        self.logger.debug("Middleware registered: %s", func.__name__)
        return func

    async def dispatch(self, ctx: Any) -> bool:
        """Backward-compatible message dispatch entry point."""

        return await self.dispatch_message(ctx)

    async def dispatch_message(self, ctx: Any) -> bool:
        for handler in self.handlers:
            if not handler.matches(getattr(ctx, "parsed_command", None)):
                continue
            if not await self._passes_filters(handler, ctx):
                continue
            await self._run_handler(handler.callback, ctx)
            return True
        parsed = getattr(ctx, "parsed_command", None)
        if parsed is not None:
            self.logger.debug("Unknown command: %s", parsed.name)
        return False

    async def dispatch_button(self, ctx: Any) -> bool:
        for handler in self.button_handlers:
            if not handler.matches(getattr(ctx, "callback_data", None)):
                continue
            if not await self._passes_filters(handler, ctx):
                continue
            await self._run_handler(handler.callback, ctx)
            return True
        return False

    async def dispatch_inline(self, ctx: Any) -> list[Any]:
        results: list[Any] = []
        for handler in self.inline_handlers:
            if not handler.matches(ctx):
                continue
            if not await self._passes_filters(handler, ctx):
                continue
            payload = await self._run_handler(handler.callback, ctx)
            if payload is None:
                continue
            if isinstance(payload, list):
                results.extend(payload)
            else:
                results.append(payload)
        return results

    def _split_items(self, items: tuple[str | FilterSpec, ...]) -> tuple[list[str], list[FilterSpec]]:
        names: list[str] = []
        filters: list[FilterSpec] = []
        for item in items:
            if isinstance(item, FilterSpec):
                filters.append(item)
            else:
                names.append(item)
        return names, filters

    def _collect_filters(self, func: HandlerCallback, extra_filters: list[FilterSpec]) -> list[FilterSpec]:
        registered = list(getattr(func, FILTER_ATTR, []))
        return [*registered, *extra_filters]

    @staticmethod
    def _track_handler(func: HandlerCallback, handler: BaseHandler) -> None:
        tracked = list(getattr(func, HANDLER_ATTR, []))
        tracked.append(handler)
        setattr(func, HANDLER_ATTR, tracked)

    async def _passes_filters(self, handler: BaseHandler, ctx: Any) -> bool:
        if handler.owner_only:
            owner_id = getattr(getattr(ctx.app, "config", None), "owner_id", None)
            if owner_id is None or ctx.user_id != owner_id:
                return False

        for spec in handler.filters:
            try:
                if not await spec.check(ctx):
                    return False
            except Exception as exc:
                self.logger.error("Filter error: %s", exc, exc_info=True)
                return False
        return True

    async def _run_handler(self, callback: HandlerCallback, ctx: Any) -> Any:
        async def invoke(index: int) -> Any:
            if index >= len(self.middlewares):
                return await callback(ctx)

            middleware = self.middlewares[index]

            async def next_handler() -> Any:
                return await invoke(index + 1)

            return await middleware(ctx, next_handler)

        try:
            return await invoke(0)
        except Exception as exc:
            self.logger.error("Handler error: %s", exc, exc_info=True)
            return None
