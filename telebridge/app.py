"""Main developer-facing application object."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any, Awaitable, Callable

from telebridge.client import UnifiedClient
from telebridge.config import TeleBridgeConfig, load_config
from telebridge.errors import ConfigurationError, TeleBridgeError
from telebridge.logger import configure_logging
from telebridge.plugin_loader import PluginLoader
from telebridge.router import Router
from telebridge.scheduler import Scheduler

TaskCallback = Callable[[], Awaitable[Any]]
MiddlewareCallback = Callable[[Any, Callable[[], Awaitable[Any]]], Awaitable[Any]]


class TeleBridgeApp:
    """High-level Telegram automation application."""

    def __init__(self) -> None:
        self.logger = configure_logging()
        self.config = TeleBridgeConfig()
        self.router = Router(self.logger)
        self.scheduler = Scheduler(self.logger)
        self.plugin_loader = PluginLoader(self.logger)
        self.client = UnifiedClient(self, self.config, self.logger)
        self._plugins_loaded = False

    def _refresh_runtime(self) -> None:
        self.logger = configure_logging(self.config.log_level)
        self.router.logger = self.logger
        self.scheduler.logger = self.logger
        self.plugin_loader.logger = self.logger
        self.client = UnifiedClient(self, self.config, self.logger)

    def setup(
        self,
        *,
        bot_token: str | None = None,
        api_id: int | None = None,
        api_hash: str | None = None,
        session_name: str | None = None,
        session_string: str | None = None,
        plugins_dir: str | None = None,
        env_file: str = ".env",
        json_config: str | None = None,
        log_level: str | None = None,
        command_prefixes: tuple[str, ...] | list[str] | str | None = None,
        auto_load_plugins: bool | None = None,
        owner_id: int | None = None,
        rate_limit: int | None = None,
        min_request_interval: float | None = None,
        delay_range: tuple[float, float] | list[float] | str | None = None,
        max_retries: int | None = None,
        queue_size: int | None = None,
        identical_message_limit: int | None = None,
        identical_message_window: float | None = None,
    ) -> "TeleBridgeApp":
        """Load configuration and rebuild runtime state."""

        self.config = load_config(
            env_file=env_file,
            json_config=json_config,
            overrides={
                "bot_token": bot_token,
                "api_id": api_id,
                "api_hash": api_hash,
                "session_name": session_name,
                "session_string": session_string,
                "plugins_dir": plugins_dir,
                "log_level": log_level,
                "command_prefixes": command_prefixes,
                "auto_load_plugins": auto_load_plugins,
                "owner_id": owner_id,
                "rate_limit": rate_limit,
                "min_request_interval": min_request_interval,
                "delay_range": delay_range,
                "max_retries": max_retries,
                "queue_size": queue_size,
                "identical_message_limit": identical_message_limit,
                "identical_message_window": identical_message_window,
            },
        )
        self._refresh_runtime()
        self._plugins_loaded = False
        return self

    def command(
        self,
        *items: Any,
        owner: bool = False,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Register a command callback."""

        return self.router.command(*items, owner=owner)

    def button(
        self,
        *items: Any,
        owner: bool = False,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Register a callback button handler."""

        return self.router.button(*items, owner=owner)

    def inline(self, *filters: Any, owner: bool = False) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Register an inline query handler."""

        return self.router.inline(*filters, owner=owner)

    def middleware(self, func: MiddlewareCallback) -> MiddlewareCallback:
        """Register a middleware callback."""

        return self.router.middleware(func)

    def task(self, *, interval: float, run_on_start: bool = False) -> Callable[[TaskCallback], TaskCallback]:
        """Register a repeating background task."""

        return self.scheduler.task(interval=interval, run_on_start=run_on_start)

    def load_plugins(self, directory: str | Path | None = None) -> list[Any]:
        """Load command plugins from disk."""

        modules = self.plugin_loader.load_from_directory(Path(directory or self.config.plugins_dir))
        self._plugins_loaded = True
        return modules

    def validate_startup(self) -> None:
        """Validate configuration and local runtime requirements."""

        self.config.validate(require_client=True)
        self._validate_dependencies()
        self._validate_plugins_dir()

    def _validate_dependencies(self) -> None:
        missing: list[str] = []
        if self.config.bot_enabled and importlib.util.find_spec("aiogram") is None:
            missing.append("aiogram>=3.0")
        if self.config.userbot_enabled and importlib.util.find_spec("telethon") is None:
            missing.append("telethon>=1.30")
        if missing:
            joined = ", ".join(missing)
            raise ConfigurationError(
                f"Missing runtime dependencies: {joined}\n"
                "Install the required packages before starting TeleBridge."
            )

    def _validate_plugins_dir(self) -> None:
        if not self.config.auto_load_plugins:
            return

        plugin_dir = Path(self.config.plugins_dir)
        if not plugin_dir.exists():
            if self.config.plugins_dir == "plugins":
                return
            raise ConfigurationError(
                f"Plugin directory not found: {plugin_dir}\n"
                "Create the directory, point plugins_dir to the correct path, or disable auto_load_plugins."
            )
        if not plugin_dir.is_dir():
            raise ConfigurationError(f"Plugin path is not a directory: {plugin_dir}")

    @staticmethod
    def _ensure_run_context() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        raise TeleBridgeError("app.run() cannot be called from an active event loop. Use 'await app.serve()' instead.")

    async def _serve(self, *, validate_startup: bool) -> None:
        """Start plugins, backends, and background tasks."""

        try:
            self.logger.info("TeleBridge starting")
            if validate_startup:
                self.validate_startup()

            self.logger.debug("Router initialized")
            await self.client.start(self.router)

            modules: list[Any] = []
            if self.config.auto_load_plugins:
                plugin_dir = Path(self.config.plugins_dir)
                if not plugin_dir.exists():
                    self.logger.debug("Plugin directory not found, skipping auto-load: %s", plugin_dir)
                elif not self._plugins_loaded:
                    modules = self.load_plugins()
                else:
                    modules = list(self.plugin_loader.loaded_modules.values())
            self.logger.info("Plugins loaded: %s", len(modules))

            await self.scheduler.start()
            self.logger.info("Scheduler started")
            await self.client.idle()
        except TeleBridgeError as exc:
            self.logger.error("%s", exc)
            raise
        except Exception as exc:
            self.logger.exception("Runtime error: %s", exc)
            raise TeleBridgeError(
                "TeleBridge encountered an unexpected runtime error. Check the logs for details."
            ) from exc
        finally:
            await self.scheduler.stop()
            await self.client.stop()

    async def serve(self) -> None:
        """Start plugins, backends, and background tasks."""

        await self._serve(validate_startup=True)

    def run(self) -> None:
        """Blocking convenience runner for scripts."""

        try:
            self._ensure_run_context()
            self.validate_startup()
        except TeleBridgeError as exc:
            self.logger.error("%s", exc)
            raise

        asyncio.run(self._serve(validate_startup=False))
