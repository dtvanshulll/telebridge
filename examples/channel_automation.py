"""Channel automation example for telebridge userbot workflows."""

from telebridge import app

TARGET_CHAT = "target_channel"

app.setup(
    api_id=12345,
    api_hash="0123456789abcdef0123456789abcdef",
    session_name="telebridge-channel-tools",
    auto_load_plugins=False,
)


@app.command("forwardlast")
async def forward_last(ctx):
    if ctx.client.user_client is None or ctx.message is None:
        await ctx.reply("Userbot client is not ready.")
        return

    await ctx.client.safe_request(
        lambda: ctx.client.user_client.forward_messages(TARGET_CHAT, ctx.message),
        label="forward_messages",
        backend=ctx.backend,
    )
    await ctx.reply("Forwarded the latest message.")


@app.command("archive")
async def archive_media(ctx):
    path = await ctx.download("downloads")
    await ctx.reply(f"Downloaded media to {path}")


@app.command("prune")
async def prune_message(ctx):
    await ctx.delete()


if __name__ == "__main__":
    app.run()
