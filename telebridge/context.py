"""Unified context passed to command, button, and inline handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telebridge.utils import ParsedCommand


@dataclass(slots=True)
class MessageHandle:
    """A lightweight wrapper around a sent Telegram message."""

    client: Any
    backend: str
    chat_id: int
    message_id: int | None
    raw_message: Any = None

    async def edit(self, text: str) -> Any:
        if self.message_id is None:
            raise ValueError("Cannot edit a message without a message_id")
        return await self.client.edit_message(self.chat_id, self.message_id, text, backend=self.backend)

    async def delete(self) -> Any:
        if self.message_id is None:
            raise ValueError("Cannot delete a message without a message_id")
        return await self.client.delete_message(self.chat_id, self.message_id, backend=self.backend)


@dataclass(slots=True)
class Context:
    """A single normalized incoming Telegram event."""

    app: Any
    client: Any
    backend: str
    message: Any
    chat_id: int
    user_id: int | None
    text: str
    message_id: int | None = None
    chat_type: str = "unknown"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    match: Any = None
    parsed_command: ParsedCommand | None = None
    callback_data: str | None = None
    callback_query: Any = None
    inline_query: Any = None
    event: Any = None

    @property
    def is_private(self) -> bool:
        return self.chat_type == "private"

    @property
    def is_group(self) -> bool:
        return self.chat_type in {"group", "supergroup"}

    async def reply(
        self,
        text: str,
        *,
        buttons: list[Any] | None = None,
        keyboard: list[list[str]] | None = None,
    ) -> MessageHandle:
        """Reply to the current event."""

        return await self.client.send_message(
            self.chat_id,
            text,
            backend=self.backend,
            reply_to_message_id=self.message_id,
            buttons=buttons,
            keyboard=keyboard,
        )

    async def edit(self, text: str) -> Any:
        """Edit the current message if supported."""

        if self.message_id is None:
            raise ValueError("Cannot edit a message without a message_id")
        return await self.client.edit_message(
            self.chat_id,
            self.message_id,
            text,
            backend=self.backend,
        )

    async def delete(self) -> Any:
        """Delete the current message."""

        if self.message_id is None:
            raise ValueError("Cannot delete a message without a message_id")
        return await self.client.delete_message(
            self.chat_id,
            self.message_id,
            backend=self.backend,
        )

    async def send_photo(self, path_or_url: str, *, caption: str | None = None) -> MessageHandle:
        return await self.client.send_photo(self.chat_id, path_or_url, backend=self.backend, caption=caption)

    async def send_video(self, path: str, *, caption: str | None = None) -> MessageHandle:
        return await self.client.send_video(self.chat_id, path, backend=self.backend, caption=caption)

    async def send_file(self, path: str, *, caption: str | None = None) -> MessageHandle:
        return await self.client.send_file(self.chat_id, path, backend=self.backend, caption=caption)

    async def send_audio(self, path: str, *, caption: str | None = None) -> MessageHandle:
        return await self.client.send_audio(self.chat_id, path, backend=self.backend, caption=caption)

    async def download(self, destination: str | Path) -> Path:
        """Download media attached to the current message."""

        return await self.client.download_media(self.message, destination, backend=self.backend)

    async def answer_callback(self, text: str | None = None, *, alert: bool = False) -> Any:
        """Answer a callback query."""

        if self.callback_query is None:
            raise ValueError("No callback query is available on this context")
        return await self.client.answer_callback(self.callback_query, backend=self.backend, text=text, alert=alert)

    @staticmethod
    def article(*, title: str, text: str, description: str | None = None) -> dict[str, str | None]:
        """Create a unified inline article descriptor."""

        return {
            "type": "article",
            "title": title,
            "text": text,
            "description": description,
        }


__all__ = ["Context", "MessageHandle"]
