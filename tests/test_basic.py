from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from telebridge import TeleBridgeApp, app, version
from telebridge.client import UnifiedClient
from telebridge.config import TeleBridgeConfig, load_config
from telebridge.context import Context, MessageHandle
from telebridge.errors import ConfigurationError
from telebridge.filters import filters
from telebridge.logger import configure_logging
from telebridge.plugin_loader import PluginLoader
from telebridge.utils import DuplicateMessageTracker, SlidingWindowRateLimiter, parse_command


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class StubClient:
    def __init__(self, *, admin: bool = False) -> None:
        self.admin = admin
        self.calls: list[tuple[str, object]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.calls.append(("send_message", {"chat_id": chat_id, "text": text, **kwargs}))
        return MessageHandle(client=self, backend=kwargs["backend"], chat_id=chat_id, message_id=101)

    async def send_photo(self, chat_id: int, path: str, **kwargs):
        self.calls.append(("send_photo", {"chat_id": chat_id, "path": path, **kwargs}))
        return MessageHandle(client=self, backend=kwargs["backend"], chat_id=chat_id, message_id=102)

    async def send_video(self, chat_id: int, path: str, **kwargs):
        self.calls.append(("send_video", {"chat_id": chat_id, "path": path, **kwargs}))
        return MessageHandle(client=self, backend=kwargs["backend"], chat_id=chat_id, message_id=103)

    async def send_file(self, chat_id: int, path: str, **kwargs):
        self.calls.append(("send_file", {"chat_id": chat_id, "path": path, **kwargs}))
        return MessageHandle(client=self, backend=kwargs["backend"], chat_id=chat_id, message_id=104)

    async def send_audio(self, chat_id: int, path: str, **kwargs):
        self.calls.append(("send_audio", {"chat_id": chat_id, "path": path, **kwargs}))
        return MessageHandle(client=self, backend=kwargs["backend"], chat_id=chat_id, message_id=105)

    async def edit_message(self, chat_id: int, message_id: int, text: str, **kwargs):
        self.calls.append(("edit_message", {"chat_id": chat_id, "message_id": message_id, "text": text, **kwargs}))
        return True

    async def delete_message(self, chat_id: int, message_id: int, **kwargs):
        self.calls.append(("delete_message", {"chat_id": chat_id, "message_id": message_id, **kwargs}))
        return True

    async def download_media(self, message, destination, **kwargs):
        path = Path(destination) / "download.bin"
        self.calls.append(("download_media", {"message": message, "destination": Path(destination), **kwargs}))
        return path

    async def answer_callback(self, callback_query, **kwargs):
        self.calls.append(("answer_callback", {"callback_query": callback_query, **kwargs}))
        return True

    async def is_chat_admin(self, chat_id: int, user_id: int | None, **kwargs) -> bool:
        self.calls.append(("is_chat_admin", {"chat_id": chat_id, "user_id": user_id, **kwargs}))
        return self.admin


def build_context(
    *,
    local_app: TeleBridgeApp,
    client: StubClient,
    text: str = "/start",
    callback_data: str | None = None,
    user_id: int = 1,
    chat_type: str = "private",
) -> Context:
    parsed = parse_command(text, local_app.config.command_prefixes)
    return Context(
        app=local_app,
        client=client,
        backend="bot",
        message={"id": 1},
        chat_id=100,
        user_id=user_id,
        text=text,
        message_id=55,
        chat_type=chat_type,
        command=parsed.name if parsed else None,
        args=parsed.args if parsed else [],
        parsed_command=parsed,
        callback_data=callback_data,
        callback_query={"id": "cb"} if callback_data else None,
    )


def test_app_instance_loads():
    assert isinstance(app, TeleBridgeApp)
    assert version == "0.1.0"


def test_command_decorator_registers_handler():
    local_app = TeleBridgeApp()

    @local_app.command("start")
    async def start(ctx):
        return ctx

    assert len(local_app.router.handlers) == 1
    assert local_app.router.handlers[0].commands == ("start",)
    assert parse_command("/start") is not None


def test_plugin_loader_imports_plugin_module_and_registers_command(tmp_path):
    logger = configure_logging("DEBUG", "telebridge-test-plugin")
    loader = PluginLoader(logger)
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_path = plugin_dir / "sample.py"
    plugin_path.write_text(
        "from telebridge import app\n\n"
        "@app.command('sample')\n"
        "async def sample(ctx):\n"
        "    return ctx\n",
        encoding="utf-8",
    )

    original_handlers = list(app.router.handlers)
    try:
        app.router.handlers.clear()
        modules = loader.load_from_directory(plugin_dir)
        assert len(modules) == 1
        assert any(handler.commands == ("sample",) for handler in app.router.handlers)
    finally:
        app.router.handlers[:] = original_handlers


def test_invalid_config_raises_error():
    local_app = TeleBridgeApp()

    with pytest.raises(ConfigurationError, match="Invalid Telegram bot token"):
        local_app.setup(bot_token="invalid-token")


def test_startup_requires_client_configuration():
    local_app = TeleBridgeApp()

    with pytest.raises(ConfigurationError, match="No Telegram client configured"):
        local_app.validate_startup()


def test_load_config_accepts_safety_overrides():
    config = load_config(
        overrides={
            "bot_token": "123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
            "rate_limit": 10,
            "min_request_interval": 0.25,
            "delay_range": (0.1, 0.2),
            "max_retries": 5,
            "queue_size": 50,
            "identical_message_limit": 2,
            "identical_message_window": 30.0,
        }
    )

    assert config.rate_limit == 10
    assert config.min_request_interval == 0.25
    assert config.delay_range == (0.1, 0.2)
    assert config.max_retries == 5
    assert config.queue_size == 50
    assert config.identical_message_limit == 2
    assert config.identical_message_window == 30.0


def test_parse_command_handles_member_descriptor_prefixes():
    handler = ListHandler()
    logger = logging.getLogger("telebridge")
    logger.addHandler(handler)

    try:
        parsed = parse_command("/ping test", TeleBridgeConfig.__dict__["command_prefixes"])
    finally:
        logger.removeHandler(handler)

    assert parsed is not None
    assert parsed.name == "ping"
    assert parsed.args == ["test"]
    assert any("Invalid prefix configuration detected" in message for message in handler.messages)


def test_load_config_invalid_prefixes_fall_back_safely():
    handler = ListHandler()
    logger = logging.getLogger("telebridge")
    logger.addHandler(handler)

    try:
        config = load_config(
            overrides={
                "bot_token": "123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
                "command_prefixes": object(),
            }
        )
    finally:
        logger.removeHandler(handler)

    assert config.command_prefixes == ("/",)
    assert any("Invalid command_prefixes" in message for message in handler.messages)


@pytest.mark.asyncio
async def test_buttons_filters_and_middleware_run():
    local_app = TeleBridgeApp()
    local_app.config = TeleBridgeConfig(owner_id=42)
    client = StubClient(admin=True)
    seen: list[str] = []

    @local_app.middleware
    async def middleware(ctx, next_call):
        seen.append(f"before:{ctx.text}")
        result = await next_call()
        seen.append("after")
        return result

    @local_app.command("ban", filters.admin)
    async def ban(ctx):
        seen.append("command")
        await ctx.reply("banned")

    @local_app.button("confirm", owner=True)
    async def confirm(ctx):
        seen.append("button")
        await ctx.answer_callback("done")

    command_ctx = build_context(local_app=local_app, client=client, text="/ban", chat_type="group")
    button_ctx = build_context(local_app=local_app, client=client, text="confirm", callback_data="confirm", user_id=42)

    assert await local_app.router.dispatch_message(command_ctx) is True
    assert await local_app.router.dispatch_button(button_ctx) is True
    assert seen == ["before:/ban", "command", "after", "before:confirm", "button", "after"]


@pytest.mark.asyncio
async def test_context_media_helpers_and_message_handle():
    local_app = TeleBridgeApp()
    client = StubClient()
    ctx = build_context(local_app=local_app, client=client, text="/media")

    handle = await ctx.reply(
        "Choose option",
        buttons=[["Option 1", "opt1"], ["Option 2", "opt2"]],
        keyboard=[["Yes", "No"]],
    )
    await handle.edit("Done")
    await ctx.send_photo("photo.jpg")
    await ctx.send_video("video.mp4")
    await ctx.send_file("file.txt")
    await ctx.send_audio("song.mp3")
    download_path = await ctx.download("downloads")
    await ctx.delete()

    assert download_path == Path("downloads") / "download.bin"
    call_names = [name for name, _ in client.calls]
    assert call_names == [
        "send_message",
        "edit_message",
        "send_photo",
        "send_video",
        "send_file",
        "send_audio",
        "download_media",
        "delete_message",
    ]


@pytest.mark.asyncio
async def test_inline_handler_returns_articles():
    local_app = TeleBridgeApp()
    client = StubClient()

    @local_app.inline()
    async def inline_handler(ctx):
        return [ctx.article(title="Hello", text="Inline response")]

    ctx = build_context(local_app=local_app, client=client, text="hello")
    results = await local_app.router.dispatch_inline(ctx)

    assert results == [{"type": "article", "title": "Hello", "text": "Inline response", "description": None}]


@pytest.mark.asyncio
async def test_handler_exception_does_not_crash_router():
    local_app = TeleBridgeApp()
    client = StubClient()
    seen: list[str] = []

    @local_app.command("boom")
    async def boom(ctx):
        raise RuntimeError("boom")

    @local_app.command("ok")
    async def ok(ctx):
        seen.append("ok")

    assert await local_app.router.dispatch_message(build_context(local_app=local_app, client=client, text="/boom")) is True
    assert await local_app.router.dispatch_message(build_context(local_app=local_app, client=client, text="/ok")) is True
    assert seen == ["ok"]


@pytest.mark.asyncio
async def test_unknown_commands_and_empty_messages_do_not_crash():
    local_app = TeleBridgeApp()
    client = StubClient()

    @local_app.command("known")
    async def known(ctx):
        return None

    assert await local_app.router.dispatch_message(build_context(local_app=local_app, client=client, text="/missing")) is False
    assert await local_app.router.dispatch_message(build_context(local_app=local_app, client=client, text="")) is False


@pytest.mark.asyncio
async def test_client_update_handlers_are_protected():
    logger = configure_logging("DEBUG", "telebridge-test-client")
    runtime_app = SimpleNamespace(config=TeleBridgeConfig())
    client = UnifiedClient(runtime_app, runtime_app.config, logger)

    class ExplodingRouter:
        async def dispatch_message(self, ctx):
            raise RuntimeError("dispatch failed")

        async def dispatch_button(self, ctx):
            raise RuntimeError("dispatch failed")

        async def dispatch_inline(self, ctx):
            raise RuntimeError("dispatch failed")

    client._router = ExplodingRouter()

    await client._on_bot_message(
        SimpleNamespace(
            text="/ping",
            caption=None,
            chat=SimpleNamespace(id=100, type="private"),
            from_user=SimpleNamespace(id=200),
            message_id=1,
        )
    )
    await client._on_bot_callback(SimpleNamespace(message=None, data="confirm", from_user=SimpleNamespace(id=200)))
    await client._on_user_message(object())
    await client._on_user_callback(object())


@pytest.mark.asyncio
async def test_duplicate_message_tracker_and_window_limiter():
    tracker = DuplicateMessageTracker(limit=2, period=60.0)
    limiter = SlidingWindowRateLimiter(max_calls=1, period=0.01)

    assert await tracker.extra_delay("hello") == 0.0
    assert await tracker.extra_delay("hello") > 0.0
    assert await limiter.wait_for_slot() == 0.0
    assert await limiter.wait_for_slot() > 0.0
