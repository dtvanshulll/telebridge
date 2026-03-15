"""Unified backend client for aiogram and Telethon."""

from __future__ import annotations

import asyncio
from getpass import getpass
from pathlib import Path
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from telebridge.context import Context, MessageHandle
from telebridge.errors import AuthenticationError, ConfigurationError
from telebridge.utils import DuplicateMessageTracker, SlidingWindowRateLimiter, parse_command

if TYPE_CHECKING:
    from telebridge.config import TeleBridgeConfig
    from telebridge.router import Router


@dataclass(slots=True)
class QueuedRequest:
    """A queued outbound API operation."""

    label: str
    backend: str
    signature: str | None
    operation: Any
    future: asyncio.Future[Any]


class UnifiedClient:
    """Bridge bot and userbot backends behind one API."""

    def __init__(self, app: Any, config: "TeleBridgeConfig", logger: Any) -> None:
        self.app = app
        self.config = config
        self.logger = logger
        self.bot: Any = None
        self.dispatcher: Any = None
        self.user_client: Any = None
        self._bot_polling_task: asyncio.Task[Any] | None = None
        self._router: Router | None = None
        self._me: Any = None
        self.request_queue: asyncio.Queue[QueuedRequest | None] | None = None
        self._request_queue: asyncio.Queue[QueuedRequest | None] | None = None
        self._queue_worker_task: asyncio.Task[Any] | None = None
        self._minute_limiter = SlidingWindowRateLimiter(self.config.rate_limit, 60.0)
        interval = max(self.config.min_request_interval, 0.001)
        self._interval_limiter = SlidingWindowRateLimiter(1, interval)
        self._duplicate_tracker = DuplicateMessageTracker(
            self.config.identical_message_limit,
            self.config.identical_message_window,
        )

    async def start(self, router: "Router") -> None:
        """Initialize enabled backends and start listening."""

        self._router = router
        await self._start_request_worker()
        if not self.config.bot_enabled and not self.config.userbot_enabled:
            raise ConfigurationError("No Telegram client configured.\nProvide bot_token or api_id/api_hash.")
        if self.config.bot_enabled:
            await self._start_bot()
        if self.config.userbot_enabled:
            await self._start_userbot()

    async def _start_bot(self) -> None:
        from aiogram import Bot, Dispatcher
        from aiogram.exceptions import TelegramUnauthorizedError

        self.bot = Bot(token=self.config.bot_token)
        try:
            await self.bot.get_me()
        except TelegramUnauthorizedError as exc:
            await self.bot.session.close()
            self.bot = None
            raise AuthenticationError(
                "Invalid Telegram bot token.\n"
                "Please check your bot_token setting or TELEBRIDGE_BOT_TOKEN environment variable."
            ) from exc
        except Exception as exc:
            await self.bot.session.close()
            self.bot = None
            raise AuthenticationError(
                "Telegram bot authentication failed.\n"
                "Please check your bot_token setting and network access."
            ) from exc

        self.dispatcher = Dispatcher()
        self.dispatcher.message.register(self._on_bot_message)
        self.dispatcher.callback_query.register(self._on_bot_callback)
        self.dispatcher.inline_query.register(self._on_bot_inline_query)
        self._bot_polling_task = asyncio.create_task(self.dispatcher.start_polling(self.bot))
        self.logger.info("Bot enabled")

    async def _start_userbot(self) -> None:
        from telethon import TelegramClient, events
        from telethon.errors import (
            ApiIdInvalidError,
            PasswordHashInvalidError,
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            PhoneNumberInvalidError,
        )
        from telethon.sessions import StringSession

        session: str | Any
        session_path = self.config.session_file_path()
        session_exists = bool(session_path and session_path.exists())

        if self.config.session_string:
            session = StringSession(self.config.session_string)
        else:
            session = self.config.session_name

        self.user_client = TelegramClient(session, self.config.api_id, self.config.api_hash)
        self.logger.info("Userbot enabled")
        try:
            await self._connect_user_client()
            authorized = await self.user_client.is_user_authorized()
            if authorized:
                if session_exists or self.config.uses_session_string:
                    self.logger.info("Existing userbot session loaded")
            else:
                if self.config.uses_session_string:
                    raise AuthenticationError(
                        "Invalid Telegram session string.\n"
                        "Provide a valid session_string or remove it to use automatic login."
                    )

                self.logger.info("Starting login process")
                await self._run_userbot_login_flow()
                self.logger.info("Login successful")
                if session_path is not None:
                    self.logger.info("Session saved")

            self._me = await self.user_client.get_me()
        except ApiIdInvalidError as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError("Invalid Telegram API_ID or API_HASH") from exc
        except PhoneCodeInvalidError as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError("Incorrect login code") from exc
        except PhoneCodeExpiredError as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError("Login code expired. Please run TeleBridge again to request a new code.") from exc
        except PasswordHashInvalidError as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError("Incorrect Telegram password") from exc
        except PhoneNumberInvalidError as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError(
                "Invalid Telegram phone number.\n"
                "Enter the number in international format, for example +123456789."
            ) from exc
        except AuthenticationError:
            await self.user_client.disconnect()
            self.user_client = None
            raise
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError("Could not connect to Telegram servers") from exc
        except Exception as exc:
            await self.user_client.disconnect()
            self.user_client = None
            raise AuthenticationError(
                "Login failed.\n"
                "Run once to create a session or provide session_string."
            ) from exc

        self.user_client.add_event_handler(self._on_user_message, events.NewMessage())
        self.user_client.add_event_handler(self._on_user_callback, events.CallbackQuery())

    async def _connect_user_client(self) -> None:
        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")

        try:
            await self._perform_with_retry("userbot_connect", "userbot", self.user_client.connect)
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            raise AuthenticationError("Could not connect to Telegram servers") from exc

    async def _run_userbot_login_flow(self) -> None:
        from telethon.errors import SessionPasswordNeededError

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")

        phone = await self._prompt("Enter your Telegram phone number: ")
        try:
            self.logger.info("Sending login code")
            sent_code = await self._perform_with_retry(
                "send_login_code",
                "userbot",
                lambda: self.user_client.send_code_request(phone),
            )
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            raise AuthenticationError("Could not connect to Telegram servers") from exc

        code = await self._prompt("Enter the login code you received: ")
        code = code.replace(" ", "")
        try:
            await self._perform_with_retry(
                "userbot_sign_in",
                "userbot",
                lambda: self.user_client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=sent_code.phone_code_hash,
                ),
            )
        except SessionPasswordNeededError:
            await asyncio.to_thread(print, "Two-step verification enabled.")
            password = await self._prompt("Enter your Telegram password: ", secret=True)
            await self._perform_with_retry(
                "userbot_password_sign_in",
                "userbot",
                lambda: self.user_client.sign_in(password=password),
            )

        if not await self.user_client.is_user_authorized():
            raise AuthenticationError(
                "Userbot authorization failed.\n"
                "Run once to create a session or provide session_string."
            )

    async def _prompt(self, prompt: str, *, secret: bool = False) -> str:
        reader = getpass if secret else input
        value = await asyncio.to_thread(reader, prompt)
        normalized = value.strip()
        if not normalized:
            raise AuthenticationError("Userbot login was cancelled because a required value was empty.")
        return normalized

    async def idle(self) -> None:
        waiters: list[Any] = []
        if self._bot_polling_task is not None:
            waiters.append(self._bot_polling_task)
        if self.user_client is not None:
            waiters.append(self.user_client.disconnected)

        if not waiters:
            return

        await asyncio.gather(*waiters)

    async def stop(self) -> None:
        if self._request_queue is not None:
            await self._request_queue.join()
        if self._request_queue is not None and self._queue_worker_task is not None:
            await self._request_queue.put(None)
            await asyncio.gather(self._queue_worker_task, return_exceptions=True)
            self._queue_worker_task = None
            self.request_queue = None
            self._request_queue = None
        if self.dispatcher is not None:
            await self.dispatcher.stop_polling()
        if self._bot_polling_task is not None:
            self._bot_polling_task.cancel()
            await asyncio.gather(self._bot_polling_task, return_exceptions=True)
            self._bot_polling_task = None
        if self.bot is not None:
            await self.bot.session.close()
        if self.user_client is not None and self.user_client.is_connected():
            await self.user_client.disconnect()

    async def _dispatch_update(self, label: str, callback: Any) -> None:
        try:
            await callback()
        except Exception as exc:
            self.logger.error("Unhandled update error in %s: %s", label, exc, exc_info=True)

    @staticmethod
    def _decode_callback_data(data: Any) -> str:
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="ignore")
        if data is None:
            return ""
        return str(data)

    async def _on_bot_message(self, message: Any) -> None:
        if self._router is None:
            return

        async def process() -> None:
            if message is None:
                self.logger.warning("Malformed bot message update received")
                return

            chat = getattr(message, "chat", None)
            text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
            parsed = parse_command(text, self.config.command_prefixes)
            ctx = Context(
                app=self.app,
                client=self,
                backend="bot",
                message=message,
                chat_id=getattr(chat, "id", 0),
                user_id=getattr(getattr(message, "from_user", None), "id", None),
                text=text,
                message_id=getattr(message, "message_id", None),
                chat_type=str(getattr(chat, "type", "unknown")),
                command=parsed.name if parsed else None,
                args=parsed.args if parsed else [],
                parsed_command=parsed,
                event=message,
            )
            await self._router.dispatch_message(ctx)

        await self._dispatch_update("_on_bot_message", process)

    async def _on_bot_callback(self, query: Any) -> None:
        if self._router is None:
            return

        async def process() -> None:
            if query is None:
                self.logger.warning("Malformed bot callback update received")
                return

            message = getattr(query, "message", None)
            chat = getattr(message, "chat", None)
            callback_data = self._decode_callback_data(getattr(query, "data", None))
            ctx = Context(
                app=self.app,
                client=self,
                backend="bot",
                message=message,
                chat_id=getattr(chat, "id", 0),
                user_id=getattr(getattr(query, "from_user", None), "id", None),
                text=callback_data,
                message_id=getattr(message, "message_id", None),
                chat_type=str(getattr(chat, "type", "unknown")),
                callback_data=callback_data,
                callback_query=query,
                event=query,
            )
            await self._router.dispatch_button(ctx)

        await self._dispatch_update("_on_bot_callback", process)

    async def _on_bot_inline_query(self, query: Any) -> None:
        if self._router is None:
            return

        async def process() -> None:
            if query is None:
                self.logger.warning("Malformed bot inline query update received")
                return

            user = getattr(query, "from_user", None)
            ctx = Context(
                app=self.app,
                client=self,
                backend="bot",
                message=None,
                chat_id=getattr(user, "id", 0),
                user_id=getattr(user, "id", None),
                text=getattr(query, "query", "") or "",
                chat_type="private",
                inline_query=query,
                event=query,
            )
            results = await self._router.dispatch_inline(ctx)
            await self.answer_inline_query(query, results)

        await self._dispatch_update("_on_bot_inline_query", process)

    async def _on_user_message(self, event: Any) -> None:
        if self._router is None:
            return

        async def process() -> None:
            if event is None:
                self.logger.warning("Malformed user message update received")
                return

            text = getattr(event, "raw_text", None) or ""
            parsed = parse_command(text, self.config.command_prefixes)
            if parsed is None:
                return

            chat = await event.get_chat() if hasattr(event, "get_chat") else None
            message = getattr(event, "message", None)
            ctx = Context(
                app=self.app,
                client=self,
                backend="userbot",
                message=message,
                chat_id=getattr(event, "chat_id", 0),
                user_id=getattr(message, "sender_id", None),
                text=text,
                message_id=getattr(message, "id", None),
                chat_type=self._telethon_chat_type(chat),
                command=parsed.name,
                args=parsed.args,
                parsed_command=parsed,
                event=event,
            )
            await self._router.dispatch_message(ctx)

        await self._dispatch_update("_on_user_message", process)

    async def _on_user_callback(self, event: Any) -> None:
        if self._router is None:
            return

        async def process() -> None:
            if event is None:
                self.logger.warning("Malformed user callback update received")
                return

            message = await event.get_message() if hasattr(event, "get_message") else None
            chat = await event.get_chat() if hasattr(event, "get_chat") else None
            callback_data = self._decode_callback_data(getattr(event, "data", b"") or b"")
            ctx = Context(
                app=self.app,
                client=self,
                backend="userbot",
                message=message,
                chat_id=getattr(event, "chat_id", 0),
                user_id=getattr(event, "sender_id", None),
                text=callback_data,
                message_id=getattr(message, "id", None),
                chat_type=self._telethon_chat_type(chat),
                callback_data=callback_data,
                callback_query=event,
                event=event,
            )
            await self._router.dispatch_button(ctx)

        await self._dispatch_update("_on_user_callback", process)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        backend: str,
        reply_to_message_id: int | None = None,
        buttons: list[Any] | None = None,
        keyboard: list[list[str]] | None = None,
    ) -> MessageHandle:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            markup = self._build_bot_markup(buttons=buttons, keyboard=keyboard)
            raw = await self.safe_request(
                lambda: self.bot.send_message(
                    chat_id,
                    text,
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=markup,
                ),
                label="send_message",
                backend=backend,
                signature=self._message_signature(text=text),
            )
            return self._wrap_message(raw, backend, chat_id)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        markup = self._build_userbot_markup(buttons=buttons, keyboard=keyboard)
        raw = await self.safe_request(
            lambda: self.user_client.send_message(chat_id, text, reply_to=reply_to_message_id, buttons=markup),
            label="send_message",
            backend=backend,
            signature=self._message_signature(text=text),
        )
        return self._wrap_message(raw, backend, chat_id)

    async def send_photo(
        self,
        chat_id: int,
        path_or_url: str,
        *,
        backend: str,
        caption: str | None = None,
    ) -> MessageHandle:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            raw = await self.safe_request(
                lambda: self.bot.send_photo(chat_id, self._bot_upload_source(path_or_url), caption=caption),
                label="send_photo",
                backend=backend,
                signature=self._message_signature(text=f"photo:{path_or_url}|{caption or ''}"),
            )
            return self._wrap_message(raw, backend, chat_id)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        raw = await self.safe_request(
            lambda: self.user_client.send_file(chat_id, path_or_url, caption=caption),
            label="send_photo",
            backend=backend,
            signature=self._message_signature(text=f"photo:{path_or_url}|{caption or ''}"),
        )
        return self._wrap_message(raw, backend, chat_id)

    async def send_video(
        self,
        chat_id: int,
        path: str,
        *,
        backend: str,
        caption: str | None = None,
    ) -> MessageHandle:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            raw = await self.safe_request(
                lambda: self.bot.send_video(chat_id, self._bot_upload_source(path), caption=caption),
                label="send_video",
                backend=backend,
                signature=self._message_signature(text=f"video:{path}|{caption or ''}"),
            )
            return self._wrap_message(raw, backend, chat_id)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        raw = await self.safe_request(
            lambda: self.user_client.send_file(chat_id, path, caption=caption),
            label="send_video",
            backend=backend,
            signature=self._message_signature(text=f"video:{path}|{caption or ''}"),
        )
        return self._wrap_message(raw, backend, chat_id)

    async def send_file(
        self,
        chat_id: int,
        path: str,
        *,
        backend: str,
        caption: str | None = None,
    ) -> MessageHandle:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            raw = await self.safe_request(
                lambda: self.bot.send_document(chat_id, self._bot_upload_source(path), caption=caption),
                label="send_file",
                backend=backend,
                signature=self._message_signature(text=f"file:{path}|{caption or ''}"),
            )
            return self._wrap_message(raw, backend, chat_id)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        raw = await self.safe_request(
            lambda: self.user_client.send_file(chat_id, path, caption=caption, force_document=True),
            label="send_file",
            backend=backend,
            signature=self._message_signature(text=f"file:{path}|{caption or ''}"),
        )
        return self._wrap_message(raw, backend, chat_id)

    async def send_audio(
        self,
        chat_id: int,
        path: str,
        *,
        backend: str,
        caption: str | None = None,
    ) -> MessageHandle:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            raw = await self.safe_request(
                lambda: self.bot.send_audio(chat_id, self._bot_upload_source(path), caption=caption),
                label="send_audio",
                backend=backend,
                signature=self._message_signature(text=f"audio:{path}|{caption or ''}"),
            )
            return self._wrap_message(raw, backend, chat_id)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        raw = await self.safe_request(
            lambda: self.user_client.send_file(chat_id, path, caption=caption),
            label="send_audio",
            backend=backend,
            signature=self._message_signature(text=f"audio:{path}|{caption or ''}"),
        )
        return self._wrap_message(raw, backend, chat_id)

    async def edit_message(self, chat_id: int, message_id: int, text: str, *, backend: str) -> Any:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            return await self.safe_request(
                lambda: self.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id),
                label="edit_message",
                backend=backend,
            )

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        return await self.safe_request(
            lambda: self.user_client.edit_message(chat_id, message_id, text),
            label="edit_message",
            backend=backend,
        )

    async def delete_message(self, chat_id: int, message_id: int, *, backend: str) -> Any:
        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            return await self.safe_request(
                lambda: self.bot.delete_message(chat_id, message_id),
                label="delete_message",
                backend=backend,
            )

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        return await self.safe_request(
            lambda: self.user_client.delete_messages(chat_id, message_id),
            label="delete_message",
            backend=backend,
        )

    async def download_media(self, message: Any, destination: str | Path, *, backend: str) -> Path:
        destination_path = Path(destination)
        destination_path.mkdir(parents=True, exist_ok=True)

        if backend == "bot":
            if self.bot is None:
                raise ConfigurationError("Bot backend is not enabled.")
            file_obj = None
            for attr in ("document", "video", "audio", "voice"):
                file_obj = getattr(message, attr, None)
                if file_obj is not None:
                    break
            if file_obj is None:
                photos = getattr(message, "photo", None)
                if photos:
                    file_obj = photos[-1]
            if file_obj is None:
                raise ConfigurationError("The current message does not contain downloadable media.")
            result = await self._perform_with_retry(
                "download_media",
                backend,
                lambda: self.bot.download(file_obj, destination=destination_path),
            )
            return Path(result)

        if self.user_client is None:
            raise ConfigurationError("Userbot backend is not enabled.")
        result = await self._perform_with_retry(
            "download_media",
            backend,
            lambda: message.download_media(file=destination_path),
        )
        if result is None:
            raise ConfigurationError("The current message does not contain downloadable media.")
        return Path(result)

    async def answer_callback(self, callback_query: Any, *, backend: str, text: str | None = None, alert: bool = False) -> Any:
        if backend == "bot":
            return await self.safe_request(
                lambda: callback_query.answer(text=text, show_alert=alert),
                label="answer_callback",
                backend=backend,
            )
        return await self.safe_request(
            lambda: callback_query.answer(message=text, alert=alert),
            label="answer_callback",
            backend=backend,
        )

    async def answer_inline_query(self, query: Any, results: list[dict[str, Any]]) -> Any:
        from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

        if self.bot is None:
            raise ConfigurationError("Bot backend is not enabled.")

        payload: list[Any] = []
        for index, item in enumerate(results, start=1):
            if item.get("type") != "article":
                continue
            payload.append(
                InlineQueryResultArticle(
                    id=str(index),
                    title=str(item.get("title", "Result")),
                    description=item.get("description"),
                    input_message_content=InputTextMessageContent(message_text=str(item.get("text", ""))),
                )
            )
        await self.safe_request(
            lambda: query.answer(payload, cache_time=0),
            label="answer_inline_query",
            backend="bot",
        )

    async def is_chat_admin(self, chat_id: int, user_id: int | None, *, backend: str) -> bool:
        if user_id is None:
            return False

        if backend == "bot":
            if self.bot is None:
                return False
            admins = await self.bot.get_chat_administrators(chat_id)
            return any(admin.user.id == user_id for admin in admins)

        if self.user_client is None:
            return False

        if self._me is not None and getattr(self._me, "id", None) == user_id:
            return True

        try:
            permissions = await self.user_client.get_permissions(chat_id, user_id)
        except Exception:
            return False

        return bool(getattr(permissions, "is_admin", False) or getattr(permissions, "is_creator", False))

    def _build_bot_markup(self, *, buttons: list[Any] | None, keyboard: list[list[str]] | None) -> Any:
        if buttons:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            inline_rows = [
                [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
                for row in self._normalize_inline_buttons(buttons)
            ]
            return InlineKeyboardMarkup(inline_keyboard=inline_rows)

        if keyboard:
            from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

            rows = [[KeyboardButton(text=value) for value in row] for row in keyboard]
            return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

        return None

    def _build_userbot_markup(self, *, buttons: list[Any] | None, keyboard: list[list[str]] | None) -> Any:
        from telethon import Button

        if buttons:
            return [
                [Button.inline(text, data=data.encode("utf-8")) for text, data in row]
                for row in self._normalize_inline_buttons(buttons)
            ]

        if keyboard:
            return [[Button.text(value, resize=True) for value in row] for row in keyboard]

        return None

    @staticmethod
    def _normalize_inline_buttons(buttons: list[Any]) -> list[list[tuple[str, str]]]:
        rows: list[list[tuple[str, str]]] = []
        for row in buttons:
            if isinstance(row, (list, tuple)) and len(row) == 2 and all(isinstance(item, str) for item in row):
                rows.append([(str(row[0]), str(row[1]))])
                continue

            nested: list[tuple[str, str]] = []
            for button in row:
                if not isinstance(button, (list, tuple)) or len(button) != 2:
                    raise ConfigurationError("Inline buttons must be provided as [text, callback_data] pairs.")
                nested.append((str(button[0]), str(button[1])))
            rows.append(nested)
        return rows

    @staticmethod
    def _bot_upload_source(source: str) -> Any:
        from aiogram.types import FSInputFile

        path = Path(source)
        if path.exists():
            return FSInputFile(str(path))
        return source

    def _wrap_message(self, raw: Any, backend: str, chat_id: int) -> MessageHandle:
        message_id = getattr(raw, "message_id", None)
        if message_id is None:
            message_id = getattr(raw, "id", None)
        return MessageHandle(client=self, backend=backend, chat_id=chat_id, message_id=message_id, raw_message=raw)

    async def safe_request(
        self,
        operation: Any,
        *,
        label: str = "request",
        backend: str = "unknown",
        signature: str | None = None,
    ) -> Any:
        """Queue a Telegram API request and await its result."""

        await self._start_request_worker()
        return await self._enqueue_request(label, backend, signature, operation)

    async def _start_request_worker(self) -> None:
        if self._request_queue is None:
            self._request_queue = asyncio.Queue(maxsize=self.config.queue_size)
            self.request_queue = self._request_queue
        if self._queue_worker_task is None or self._queue_worker_task.done():
            self._queue_worker_task = asyncio.create_task(self._request_worker())

    async def _request_worker(self) -> None:
        if self._request_queue is None:
            return

        while True:
            request = await self._request_queue.get()
            if request is None:
                self._request_queue.task_done()
                break

            try:
                await self._apply_safety_controls(request.signature)
                result = await self._perform_with_retry(request.label, request.backend, request.operation)
                if not request.future.cancelled():
                    request.future.set_result(result)
                self.logger.info("Request executed: %s", request.label)
            except Exception as exc:
                self.logger.error("Request failed: %s", request.label, exc_info=True)
                if not request.future.cancelled():
                    request.future.set_exception(exc)
            finally:
                self._request_queue.task_done()

    async def _enqueue_request(
        self,
        label: str,
        backend: str,
        signature: str | None,
        operation: Any,
    ) -> Any:
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        if self._request_queue is None:
            raise RuntimeError("Request queue is not running.")

        await self._request_queue.put(
            QueuedRequest(
                label=label,
                backend=backend,
                signature=signature,
                operation=operation,
                future=future,
            )
        )
        self.logger.info("Request queued: %s", label)
        return await future

    async def _apply_safety_controls(self, signature: str | None) -> None:
        waited_minute = await self._minute_limiter.wait_for_slot()
        waited_interval = await self._interval_limiter.wait_for_slot()
        if waited_minute > 0 or waited_interval > 0:
            self.logger.warning("Rate limit reached")

        duplicate_delay = await self._duplicate_tracker.extra_delay(signature)
        if duplicate_delay > 0:
            self.logger.warning("Rate limit reached")
            await asyncio.sleep(duplicate_delay)

        low, high = self.config.delay_range
        if high > 0:
            await asyncio.sleep(random.uniform(low, high))

    async def _perform_with_retry(self, label: str, backend: str, operation: Any) -> Any:
        try:
            from telethon.errors import FloodWaitError
        except Exception:  # pragma: no cover - optional while telethon is unavailable
            FloodWaitError = None

        try:
            from aiogram.exceptions import TelegramRetryAfter
        except Exception:  # pragma: no cover - optional while aiogram is unavailable
            TelegramRetryAfter = None

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return await operation()
            except Exception as exc:
                retry_after = None
                if FloodWaitError is not None and isinstance(exc, FloodWaitError):
                    last_error = exc
                    retry_after = max(int(getattr(exc, "seconds", 0)), 1)
                    self.logger.warning("Flood wait triggered (%s seconds)", retry_after)
                    await asyncio.sleep(retry_after)
                elif TelegramRetryAfter is not None and isinstance(exc, TelegramRetryAfter):
                    last_error = exc
                    retry_after = max(int(getattr(exc, "retry_after", 0)), 1)
                    self.logger.warning("Flood wait triggered (%s seconds)", retry_after)
                    await asyncio.sleep(retry_after)
                elif isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
                    last_error = exc
                else:
                    raise

                if retry_after is None:
                    last_error = exc

            if attempt < self.config.max_retries:
                self.logger.info("Retrying request: %s", label)
                await asyncio.sleep(min(float(attempt), 3.0))

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Request failed without a captured exception: {label}")

    @staticmethod
    def _message_signature(*, text: str) -> str:
        return " ".join(text.strip().split()).lower()

    @staticmethod
    def _telethon_chat_type(chat: Any) -> str:
        if chat is None:
            return "unknown"
        if getattr(chat, "broadcast", False):
            return "channel"
        if getattr(chat, "megagroup", False):
            return "supergroup"
        if getattr(chat, "title", None):
            return "group"
        return "private"
