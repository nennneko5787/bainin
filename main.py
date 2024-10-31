import asyncio
import os
from contextlib import asynccontextmanager

import discord
import dotenv
from discord.ext import commands
from fastapi import FastAPI

from cogs.database import Database

dotenv.load_dotenv()

discord.utils.setup_logging()

bot = commands.Bot("takoyaki#", intents=discord.Intents.default())


@bot.event
async def on_ready():
    await bot.tree.sync()


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.link")
    await bot.load_extension("cogs.jihanki_edit")
    await bot.load_extension("cogs.jihanki_panel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database.connect()
    asyncio.create_task(bot.start(os.getenv("discord")))
    yield


app = FastAPI(lifespan=lifespan)
