import asyncio
import os
from contextlib import asynccontextmanager

import discord
import dotenv
from discord.ext import commands, tasks
from fastapi import FastAPI

from cogs.database import Database

dotenv.load_dotenv()

discord.utils.setup_logging()

bot = commands.Bot("takoyaki#", intents=discord.Intents.default())


@bot.command("check")
async def checkCommand(ctx: commands.Context, service: str, userId: int):
    if ctx.author.id != 1048448686914551879:
        return

    row = await Database.pool.fetchrow(f"SELECT * FROM {service} WHERE id = $1", userId)

    if row:
        await ctx.reply(f"存在します\n```\nID: {row['id']}```")
    else:
        await ctx.reply("存在しません")


@bot.command("dmsend")
async def dmSendCommand(ctx: commands.Context, *, message: str):
    if ctx.author.id != 1048448686914551879:
        return

    _users = await Database.pool.fetch("SELECT owner_id FROM jihanki")

    jUsers = [user["owner_id"] for user in _users]

    _users = await Database.pool.fetch(
        "SELECT * FROM kyash"
    ) + await Database.pool.fetch("SELECT * FROM paypay")

    _users = [user["id"] for user in _users] + jUsers

    users = list(set(_users))

    for u in users:
        user = await bot.fetch_user(u)
        try:
            await user.send(message)
        except:
            pass
    await ctx.reply("successful")


@bot.command("jsend")
async def jSendCommand(ctx: commands.Context, *, message: str):
    if ctx.author.id != 1048448686914551879:
        return

    _users = await Database.pool.fetch("SELECT owner_id FROM jihanki")

    users = list(set([user["owner_id"] for user in _users]))

    for u in users:
        user = await bot.fetch_user(u)
        try:
            await user.send(message)
        except:
            pass
    await ctx.reply("successful")


@tasks.loop(seconds=20)
async def precenseLoop():
    appInfo = await bot.application_info()
    game = discord.Game(
        f"/help | {len(bot.guilds)} servers | {appInfo.approximate_user_install_count} users"
    )
    await bot.change_presence(status=discord.Status.online, activity=game)


@bot.event
async def on_ready():
    await bot.tree.sync()
    precenseLoop.start()


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.link")
    await bot.load_extension("cogs.jihanki_edit")
    await bot.load_extension("cogs.jihanki_panel")
    await bot.load_extension("cogs.send_money")
    await bot.load_extension("cogs.claim_money")
    await bot.load_extension("cogs.help")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database.connect()
    asyncio.create_task(bot.start(os.getenv("discord")))
    yield
    async with asyncio.timeout(60):
        await Database.pool.close()


app = FastAPI(lifespan=lifespan)
