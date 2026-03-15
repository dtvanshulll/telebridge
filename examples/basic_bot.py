"""Basic bot example for telebridge."""

from telebridge import app

app.setup(
    bot_token="123456:ABCdefGhIJKlmNOpQRstuVWxyZ0123456789",
    auto_load_plugins=False,
)


@app.command("start")
async def start(ctx):
    await ctx.reply("Welcome to TeleBridge.")


@app.command("delete")
async def delete_demo(ctx):
    reply = await ctx.reply("This message will be deleted.")
    await reply.delete()


if __name__ == "__main__":
    app.run()
