"""Custom exceptions used across telebridge."""

from __future__ import annotations


class TeleBridgeError(Exception):
    """Base exception for telebridge runtime and configuration errors."""


class ConfigurationError(TeleBridgeError):
    """Raised when application configuration is invalid."""


class AuthenticationError(TeleBridgeError):
    """Raised when Telegram authentication fails."""
