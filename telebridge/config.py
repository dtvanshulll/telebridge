"""Configuration loading helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from telebridge.errors import ConfigurationError
from telebridge.utils import normalize_command_prefixes

ENV_ALIASES = {
    "telebridge_bot_token": "bot_token",
    "telebridge_api_id": "api_id",
    "telebridge_api_hash": "api_hash",
    "telebridge_session_name": "session_name",
    "telebridge_session_string": "session_string",
    "telebridge_plugins_dir": "plugins_dir",
    "telebridge_log_level": "log_level",
    "telebridge_command_prefixes": "command_prefixes",
    "telebridge_auto_load_plugins": "auto_load_plugins",
    "telebridge_owner_id": "owner_id",
    "telebridge_rate_limit": "rate_limit",
    "telebridge_min_request_interval": "min_request_interval",
    "telebridge_delay_range": "delay_range",
    "telebridge_max_retries": "max_retries",
    "telebridge_queue_size": "queue_size",
    "telebridge_identical_message_limit": "identical_message_limit",
    "telebridge_identical_message_window": "identical_message_window",
}
FALSE_VALUES = {"0", "false", "no", "off"}
BOT_TOKEN_PATTERN = re.compile(r"^\d+:[A-Za-z0-9_-]{35,}$")
API_HASH_LENGTH = 32
DEFAULT_RATE_LIMIT = 20
DEFAULT_MIN_REQUEST_INTERVAL = 1.0
DEFAULT_COMMAND_PREFIXES = ("/", ".", "!")
SAFE_COMMAND_PREFIXES = ("/",)
DEFAULT_AUTO_LOAD_PLUGINS = True
DEFAULT_DELAY_RANGE = (0.5, 2.0)
DEFAULT_MAX_RETRIES = 3
DEFAULT_QUEUE_SIZE = 100
DEFAULT_IDENTICAL_MESSAGE_LIMIT = 3
DEFAULT_IDENTICAL_MESSAGE_WINDOW = 60.0
logger = logging.getLogger("telebridge")


def _normalize_key(key: str) -> str:
    normalized = key.strip().lower()
    return ENV_ALIASES.get(normalized, normalized)


def _normalize_mapping(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        normalized[_normalize_key(key)] = value
    return normalized


def _read_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}

    raw_values = dotenv_values(env_path)
    values: dict[str, str] = {}
    for key, value in raw_values.items():
        if key is None or value is None:
            continue
        values[_normalize_key(key)] = value
    return values


def _read_json_file(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON config file: {json_path}\n"
            "Please check the file for syntax errors."
        ) from exc
    if not isinstance(payload, dict):
        raise ConfigurationError("JSON config must contain an object at the top level.")
    return _normalize_mapping(payload)


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            "Invalid Telegram API credentials.\n"
            "Check API_ID and API_HASH. TELEBRIDGE_API_ID must be an integer."
        ) from exc


def _parse_prefixes(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value in (None, ""):
        return default

    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
        prefixes = tuple(part for part in items if part)
        if prefixes:
            return prefixes
        logger.warning("Invalid command_prefixes, using default '/'")
        return SAFE_COMMAND_PREFIXES

    if not isinstance(value, (list, tuple, set)):
        logger.warning("Invalid command_prefixes, using default '/'")
        return SAFE_COMMAND_PREFIXES

    return normalize_command_prefixes(value, default=SAFE_COMMAND_PREFIXES)


def _parse_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() not in FALSE_VALUES


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Expected a numeric value, got {value!r}.") from exc


def _parse_delay_range(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if value in (None, ""):
        return default

    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in value]

    if len(parts) != 2:
        raise ConfigurationError("delay_range must contain exactly two numeric values.")

    start = _float_or_none(parts[0])
    end = _float_or_none(parts[1])
    if start is None or end is None:
        raise ConfigurationError("delay_range must contain exactly two numeric values.")
    return (start, end)


@dataclass(slots=True)
class TeleBridgeConfig:
    """Application configuration shared across the app."""

    bot_token: str | None = None
    api_id: int | None = None
    api_hash: str | None = None
    session_name: str = "telebridge"
    session_string: str | None = None
    plugins_dir: str = "plugins"
    env_file: str = ".env"
    json_config: str | None = None
    log_level: str = "INFO"
    command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES
    auto_load_plugins: bool = DEFAULT_AUTO_LOAD_PLUGINS
    owner_id: int | None = None
    rate_limit: int = DEFAULT_RATE_LIMIT
    min_request_interval: float = DEFAULT_MIN_REQUEST_INTERVAL
    delay_range: tuple[float, float] = DEFAULT_DELAY_RANGE
    max_retries: int = DEFAULT_MAX_RETRIES
    queue_size: int = DEFAULT_QUEUE_SIZE
    identical_message_limit: int = DEFAULT_IDENTICAL_MESSAGE_LIMIT
    identical_message_window: float = DEFAULT_IDENTICAL_MESSAGE_WINDOW

    def __post_init__(self) -> None:
        prefixes = self.command_prefixes
        if isinstance(prefixes, str):
            prefixes = _parse_prefixes(prefixes, DEFAULT_COMMAND_PREFIXES)
        else:
            prefixes = normalize_command_prefixes(prefixes, default=DEFAULT_COMMAND_PREFIXES)
        self.command_prefixes = prefixes
        if not isinstance(self.auto_load_plugins, bool):
            self.auto_load_plugins = bool(self.auto_load_plugins)

    @property
    def bot_enabled(self) -> bool:
        return bool(self.bot_token)

    @property
    def userbot_enabled(self) -> bool:
        return bool(self.api_id and self.api_hash)

    @property
    def uses_session_string(self) -> bool:
        return bool(self.session_string)

    def session_file_path(self) -> Path | None:
        """Return the local Telethon session path when using file-backed sessions."""

        if self.uses_session_string:
            return None

        session_path = Path(self.session_name)
        if session_path.suffix != ".session":
            session_path = session_path.with_suffix(".session")
        return session_path

    def validation_errors(self) -> list[str]:
        """Return human-readable configuration issues."""

        errors: list[str] = []
        if self.bot_token and not BOT_TOKEN_PATTERN.fullmatch(self.bot_token.strip()):
            errors.append(
                "Invalid Telegram bot token.\n"
                "Please check your bot_token setting or TELEBRIDGE_BOT_TOKEN environment variable."
            )
        if self.api_id is None and self.api_hash:
            errors.append("Invalid Telegram API credentials.\nCheck API_ID and API_HASH.")
        if self.api_id is not None:
            if not isinstance(self.api_id, int):
                errors.append("Invalid Telegram API credentials.\nCheck API_ID and API_HASH.")
            elif self.api_id <= 0:
                errors.append("API_ID must be a positive integer.")
        if self.api_id is not None and not self.api_hash:
            errors.append("Invalid Telegram API credentials.\nCheck API_ID and API_HASH.")
        if self.api_hash is not None:
            if not isinstance(self.api_hash, str) or len(self.api_hash.strip()) != API_HASH_LENGTH:
                errors.append(
                    "Invalid Telegram API credentials.\n"
                    f"Check API_ID and API_HASH. API_HASH must be a {API_HASH_LENGTH}-character string."
                )
        if self.owner_id is not None and self.owner_id <= 0:
            errors.append("owner_id must be a positive integer.")
        if self.rate_limit <= 0:
            errors.append("rate_limit must be a positive integer.")
        if self.min_request_interval < 0:
            errors.append("min_request_interval must be zero or greater.")
        if self.delay_range[0] < 0 or self.delay_range[1] < 0:
            errors.append("delay_range values must be zero or greater.")
        if self.delay_range[0] > self.delay_range[1]:
            errors.append("delay_range start must be less than or equal to the end value.")
        if self.max_retries <= 0:
            errors.append("max_retries must be a positive integer.")
        if self.queue_size <= 0:
            errors.append("queue_size must be a positive integer.")
        if self.identical_message_limit <= 0:
            errors.append("identical_message_limit must be a positive integer.")
        if self.identical_message_window <= 0:
            errors.append("identical_message_window must be a positive number.")
        return errors

    def validate(self, *, require_client: bool = False) -> None:
        """Raise ConfigurationError when the config is invalid."""

        errors = self.validation_errors()
        if require_client and not self.bot_enabled and not self.userbot_enabled:
            errors.append("No Telegram client configured.\nProvide bot_token or api_id/api_hash.")

        if errors:
            raise ConfigurationError("\n".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(
    *,
    env_file: str = ".env",
    json_config: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> TeleBridgeConfig:
    """Load configuration from .env, JSON, environment variables, then explicit overrides."""

    values: dict[str, Any] = {
        "env_file": env_file,
        "json_config": json_config,
    }
    values.update(_read_env_file(env_file))

    if json_config:
        values.update(_read_json_file(json_config))

    env_values = _normalize_mapping(
        {
            "TELEBRIDGE_BOT_TOKEN": os.getenv("TELEBRIDGE_BOT_TOKEN"),
            "TELEBRIDGE_API_ID": os.getenv("TELEBRIDGE_API_ID"),
            "TELEBRIDGE_API_HASH": os.getenv("TELEBRIDGE_API_HASH"),
            "TELEBRIDGE_SESSION_NAME": os.getenv("TELEBRIDGE_SESSION_NAME"),
            "TELEBRIDGE_SESSION_STRING": os.getenv("TELEBRIDGE_SESSION_STRING"),
            "TELEBRIDGE_PLUGINS_DIR": os.getenv("TELEBRIDGE_PLUGINS_DIR"),
            "TELEBRIDGE_LOG_LEVEL": os.getenv("TELEBRIDGE_LOG_LEVEL"),
            "TELEBRIDGE_COMMAND_PREFIXES": os.getenv("TELEBRIDGE_COMMAND_PREFIXES"),
            "TELEBRIDGE_AUTO_LOAD_PLUGINS": os.getenv("TELEBRIDGE_AUTO_LOAD_PLUGINS"),
            "TELEBRIDGE_OWNER_ID": os.getenv("TELEBRIDGE_OWNER_ID"),
            "TELEBRIDGE_RATE_LIMIT": os.getenv("TELEBRIDGE_RATE_LIMIT"),
            "TELEBRIDGE_MIN_REQUEST_INTERVAL": os.getenv("TELEBRIDGE_MIN_REQUEST_INTERVAL"),
            "TELEBRIDGE_DELAY_RANGE": os.getenv("TELEBRIDGE_DELAY_RANGE"),
            "TELEBRIDGE_MAX_RETRIES": os.getenv("TELEBRIDGE_MAX_RETRIES"),
            "TELEBRIDGE_QUEUE_SIZE": os.getenv("TELEBRIDGE_QUEUE_SIZE"),
            "TELEBRIDGE_IDENTICAL_MESSAGE_LIMIT": os.getenv("TELEBRIDGE_IDENTICAL_MESSAGE_LIMIT"),
            "TELEBRIDGE_IDENTICAL_MESSAGE_WINDOW": os.getenv("TELEBRIDGE_IDENTICAL_MESSAGE_WINDOW"),
        }
    )
    values.update({key: value for key, value in env_values.items() if value not in (None, "")})

    if overrides:
        values.update({key: value for key, value in overrides.items() if value is not None})

    values["api_id"] = _int_or_none(values.get("api_id"))
    values["command_prefixes"] = _parse_prefixes(
        values.get("command_prefixes"),
        DEFAULT_COMMAND_PREFIXES,
    )
    values["owner_id"] = _int_or_none(values.get("owner_id"))
    values["rate_limit"] = _int_or_none(values.get("rate_limit")) or DEFAULT_RATE_LIMIT
    values["min_request_interval"] = _float_or_none(values.get("min_request_interval"))
    if values["min_request_interval"] is None:
        values["min_request_interval"] = DEFAULT_MIN_REQUEST_INTERVAL
    values["delay_range"] = _parse_delay_range(values.get("delay_range"), DEFAULT_DELAY_RANGE)
    values["max_retries"] = _int_or_none(values.get("max_retries")) or DEFAULT_MAX_RETRIES
    values["queue_size"] = _int_or_none(values.get("queue_size")) or DEFAULT_QUEUE_SIZE
    values["identical_message_limit"] = (
        _int_or_none(values.get("identical_message_limit")) or DEFAULT_IDENTICAL_MESSAGE_LIMIT
    )
    values["identical_message_window"] = _float_or_none(values.get("identical_message_window"))
    if values["identical_message_window"] is None:
        values["identical_message_window"] = DEFAULT_IDENTICAL_MESSAGE_WINDOW
    values["auto_load_plugins"] = _parse_bool(
        values.get("auto_load_plugins"),
        DEFAULT_AUTO_LOAD_PLUGINS,
    )

    filtered = {key: value for key, value in values.items() if key in TeleBridgeConfig.__dataclass_fields__}
    config = TeleBridgeConfig(**filtered)
    config.validate()
    return config
