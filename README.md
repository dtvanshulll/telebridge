# TeleBridge

<p align="center">
  <b>A unified Python framework for building Telegram Bots and Userbots.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/dtvanshulll/telebridge?style=flat-square">
  <img src="https://img.shields.io/github/forks/dtvanshulll/telebridge?style=flat-square">
  <img src="https://img.shields.io/github/issues/dtvanshulll/telebridge?style=flat-square">
  <img src="https://img.shields.io/github/license/dtvanshulll/telebridge?style=flat-square">
  <img src="https://img.shields.io/github/languages/top/dtvanshulll/telebridge?style=flat-square">
</p>

---

## Overview

**TeleBridge** is a Python framework that simplifies the development of **Telegram automation tools**. It provides a unified interface that allows developers to build both **Telegram bots** and **Telegram userbots** using a single asynchronous framework.

TeleBridge integrates two major Telegram ecosystems:

* **aiogram** — for Telegram Bot API development
* **telethon** — for Telegram MTProto user account automation

By combining these systems into one framework, TeleBridge removes the need to manage separate infrastructures for bots and user accounts.

---

## Why TeleBridge

Developers building Telegram automation tools often encounter several limitations:

* Bot API libraries cannot access full Telegram account capabilities
* Userbot libraries provide powerful access but lack structured frameworks
* Combining bot and userbot systems usually requires large infrastructure code

TeleBridge solves these issues by providing built-in systems such as:

* unified command routing
* plugin architecture
* middleware system
* background task scheduler
* safe Telegram request queue

The goal is to allow developers to focus on **automation logic instead of framework infrastructure**.

---

## Features

* Unified API for bots and userbots
* Async-first architecture
* Decorator-based command system
* Plugin support for modular features
* Middleware system
* Built-in background scheduler
* Automatic userbot login flow
* Request safety system with rate-limit handling

---

## Quick Example

Example TeleBridge application:

```python
from telebridge import app

app.setup(
    bot_token="BOT_TOKEN",
    api_id=12345,
    api_hash="API_HASH"
)

@app.command("ping")
async def ping(ctx):
    await ctx.reply("pong")

app.run()
```

This starts both the **Telegram bot client** and the **userbot client** in a single runtime.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/dtvanshulll/telebridge.git
cd telebridge
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Basic Usage

Initialize TeleBridge:

```python
from telebridge import app

app.setup(
    bot_token="YOUR_BOT_TOKEN",
    api_id=12345,
    api_hash="YOUR_API_HASH"
)
```

Create a command:

```python
@app.command("hello")
async def hello(ctx):
    await ctx.reply("Hello from TeleBridge")
```

Run the application:

```python
app.run()
```

---

## Project Structure

```
telebridge/
│
├── telebridge/        # framework source code
├── examples/          # example applications
├── tests/             # test suite
├── scripts/           # development utilities
```

---

## What You Can Build

TeleBridge is designed for **automation-heavy Telegram applications**.

Examples include:

### Telegram Bots

* moderation bots
* notification bots
* command systems

### Userbot Tools

* channel management tools
* message cleanup utilities
* media download automation

### Automation Systems

* channel mirroring
* scheduled automation tasks
* message processing pipelines

---

## Architecture

```
Developer Code
      │
      ▼
  TeleBridge App
      │
 ┌───────────────┐
 │ Command Router│
 └───────────────┘
      │
 ┌───────────────┐
 │ Middleware    │
 └───────────────┘
      │
 ┌───────────────┐
 │ Request Queue │
 └───────────────┘
      │
 ┌───────────────┬───────────────┐
 │ Telegram Bot  │ Telegram User │
 │ (aiogram)     │ (telethon)    │
 └───────────────┴───────────────┘
```

---

## Contributing

Contributions are welcome.

Steps:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Submit a pull request

---

## License

This project is released under the **MIT License**.

---

## Author

**Anshul Dubey**

GitHub
https://github.com/dtvanshulll

Telegram
https://t.me/dtvanshul
