<<<<<<< HEAD
# TeleBridge

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![GitHub Repo](https://img.shields.io/badge/github-telebridge-black)

`telebridge` is a unified Telegram automation framework for developers who want one async API for both Telegram bots and Telegram user accounts. It combines `aiogram` for the Bot API and `telethon` for MTProto userbot workflows behind one decorator-first application object.

GitHub Repository:
https://github.com/dtvanshull/telebridge

## Introduction

With `telebridge`, you can build command-driven Telegram automations without wiring separate dispatchers, schedulers, plugin systems, and queue safety layers by hand. One `app` instance can run bot mode, userbot mode, or both together while sharing handlers, middleware, plugins, and outbound safety controls.

## Source Code

The TeleBridge source code and examples are available on GitHub:

https://github.com/dtvanshull/telebridge

Use the repository to:

- browse the full source code
- review runnable examples in `examples/`
- report bugs in the issue tracker
- contribute fixes, features, and documentation improvements

## Features

- Unified `from telebridge import app` developer experience
- Telegram Bot API support with `aiogram`
- Telegram userbot support with `telethon`
- Command decorators for bot and userbot handlers
- Plugin loading from a directory
- Middleware support
- Background scheduler for recurring jobs
- Safe outbound request queue with retries, rate limiting, and flood wait handling
- OTP login flow for userbot sessions
- Inline buttons and callback handling
- Message editing and deletion helpers
- Media sending and downloading utilities

## Installation

Install from PyPI:

```bash
pip install telebridge
```

Install for local development:

```bash
pip install -e .[dev]
```

## Quick Start

```python
from telebridge import app

app.setup(
    bot_token="123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
    api_id=12345,
    api_hash="0123456789abcdef0123456789abcdef",
)


@app.command("start")
async def start(ctx):
    await ctx.reply("TeleBridge is ready.")


app.run()
```

## Bot Example

See [`examples/basic_bot.py`](examples/basic_bot.py).

```python
from telebridge import app

app.setup(
    bot_token="123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
    auto_load_plugins=False,
)


@app.command("ping")
async def ping(ctx):
    await ctx.reply("pong")


if __name__ == "__main__":
    app.run()
```

## Userbot Login Example

See [`examples/userbot_login.py`](examples/userbot_login.py).

```python
from telebridge import app

app.setup(
    api_id=12345,
    api_hash="0123456789abcdef0123456789abcdef",
    session_name="telebridge-user",
    auto_load_plugins=False,
)


@app.command("ping")
async def ping(ctx):
    await ctx.reply("pong from your userbot")


if __name__ == "__main__":
    app.run()
```

`telebridge` prompts for the phone number, login code, and optional 2FA password when a valid session is not already available.

## Plugin Example

Plugins are regular Python files loaded from a directory.

```python
from telebridge import app


@app.command("hello")
async def hello(ctx):
    await ctx.reply("Hello from a plugin")
```

```python
from telebridge import app

app.setup(
    bot_token="123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
    plugins_dir="plugins",
)


if __name__ == "__main__":
    app.run()
```

## Middleware Example

```python
from telebridge import app


@app.middleware
async def access_log(ctx, next_call):
    print(f"{ctx.backend}: {ctx.text}")
    return await next_call()
```

## Message Deletion Example

```python
from telebridge import app


@app.command("cleanup")
async def cleanup(ctx):
    reply = await ctx.reply("This message will be deleted.")
    await reply.delete()
```

## Channel Automation Example

See [`examples/channel_automation.py`](examples/channel_automation.py).

```python
from telebridge import app

app.setup(
    api_id=12345,
    api_hash="0123456789abcdef0123456789abcdef",
    session_name="telebridge-channel-tools",
    auto_load_plugins=False,
)


@app.command("forwardlast")
async def forward_last(ctx):
    if ctx.client.user_client is None:
        return
    await ctx.client.safe_request(
        lambda: ctx.client.user_client.forward_messages("target_channel", ctx.message),
        label="forward_messages",
        backend=ctx.backend,
    )
```

## Contributing

1. Install development dependencies with `pip install -e .[dev]`.
2. Update code, tests, and examples together.
3. Run `python scripts/release_check.py`, `pytest`, and `python -m build`.
4. Review the generated `dist/` artifacts before publishing.

## License

Released under the MIT License. See [`LICENSE`](LICENSE).
=======
# telebridge
TeleBridge is a powerful Telegram automation framework combining Bot API and Userbot capabilities to build bots, channel automation tools, media downloaders, message forwarders, and Telegram utilities.
>>>>>>> 7a48e8cec5631005cdb3aa8f66f27aaec256b10b
