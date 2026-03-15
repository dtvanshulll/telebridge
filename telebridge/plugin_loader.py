"""Automatic plugin discovery and import helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from telebridge.errors import ConfigurationError, TeleBridgeError


class PluginLoader:
    """Load plugin modules from a directory on disk."""

    def __init__(self, logger: object) -> None:
        self.logger = logger
        self.loaded_modules: dict[str, ModuleType] = {}

    @staticmethod
    def _module_name(file_path: Path) -> str:
        digest = hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()[:10]
        return f"telebridge_plugin_{file_path.stem}_{digest}"

    def load_from_directory(self, directory: str | Path) -> list[ModuleType]:
        plugin_dir = Path(directory)
        if not plugin_dir.exists():
            raise ConfigurationError(
                f"Plugin directory not found: {plugin_dir}\n"
                "Create the directory, point plugins_dir to the correct path, or disable auto_load_plugins."
            )
        if not plugin_dir.is_dir():
            raise ConfigurationError(f"Plugin path is not a directory: {plugin_dir}")

        modules: list[ModuleType] = []
        for file_path in sorted(plugin_dir.glob("*.py")):
            if file_path.name.startswith("_"):
                continue

            module_name = self._module_name(file_path)
            cached = self.loaded_modules.get(module_name)
            if cached is not None:
                modules.append(cached)
                continue

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise TeleBridgeError(f"Unable to load plugin module from {file_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as exc:
                sys.modules.pop(module_name, None)
                self.logger.exception("Plugin load failed: %s", file_path.stem)
                raise TeleBridgeError(
                    f"Failed to load plugin '{file_path.stem}'. Check the plugin for import or syntax errors."
                ) from exc
            self.loaded_modules[module_name] = module
            self.logger.info("Plugin loaded: %s", file_path.stem)
            modules.append(module)

        return modules
