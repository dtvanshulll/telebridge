"""Userbot login example for telebridge."""

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


@app.command("download")
async def download_media(ctx):
    path = await ctx.download("downloads")
    await ctx.reply(f"Saved media to {path}")


if __name__ == "__main__":
    app.run()
