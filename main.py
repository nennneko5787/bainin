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


@tasks.loop(seconds=20)
async def precenseLoop():
    game = discord.Game(f"{len(bot.guilds)} サーバー")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database.connect()
    asyncio.create_task(bot.start(os.getenv("discord")))
    yield
    async with asyncio.timeout(60):
        await Database.pool.close()


app = FastAPI(lifespan=lifespan)
