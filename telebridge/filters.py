"""Declarative filters for handlers."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Pattern

FILTER_ATTR = "_telebridge_filters"
HANDLER_ATTR = "_telebridge_handlers"
FilterCheck = Callable[[Any], bool | Awaitable[bool]]


@dataclass(slots=True)
class FilterSpec:
    """A named filter that can also be used as a decorator."""

    name: str
    callback: FilterCheck
    pattern: Pattern[str] | None = None

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        existing = list(getattr(func, FILTER_ATTR, []))
        existing.append(self)
        setattr(func, FILTER_ATTR, existing)

        for handler in getattr(func, HANDLER_ATTR, []):
            handler.filters.append(self)

        return func

    async def check(self, ctx: Any) -> bool:
        result = self.callback(ctx)
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)


class FilterFactory:
    """Create reusable filter specifications."""

    @property
    def private(self) -> FilterSpec:
        return FilterSpec("private", lambda ctx: ctx.is_private)

    @property
    def group(self) -> FilterSpec:
        return FilterSpec("group", lambda ctx: ctx.is_group)

    @property
    def admin(self) -> FilterSpec:
        return FilterSpec(
            "admin",
            lambda ctx: ctx.client.is_chat_admin(ctx.chat_id, ctx.user_id, backend=ctx.backend),
        )

    def regex(self, pattern: str) -> FilterSpec:
        compiled = re.compile(pattern)

        async def matcher(ctx: Any) -> bool:
            match = compiled.search(ctx.text or "")
            if match:
                ctx.match = match
                return True
            return False

        return FilterSpec(f"regex:{pattern}", matcher, pattern=compiled)


filters = FilterFactory()
filter = filters

__all__ = ["FILTER_ATTR", "HANDLER_ATTR", "FilterSpec", "filters", "filter"]
