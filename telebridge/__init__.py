"""Public package interface for telebridge."""

from .app import TeleBridgeApp
from .version import version

app = TeleBridgeApp()

__all__ = ["app", "TeleBridgeApp", "version"]
