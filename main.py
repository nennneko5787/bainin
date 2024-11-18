import asyncio
import os
from contextlib import asynccontextmanager

import discord
import dotenv
from discord.ext import commands, tasks
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.templating import Jinja2Templates

from cogs.database import Database

dotenv.load_dotenv()

discord.utils.setup_logging()

bot = commands.Bot("takoyaki#", intents=discord.Intents.default())


@tasks.loop(seconds=20)
async def precenseLoop():
    appInfo = await bot.application_info()
    game = discord.Game(
        f"/help | {len(bot.guilds)} servers | {appInfo.approximate_user_install_count} users"
    )
    await bot.change_presence(status=discord.Status.online, activity=game)


@bot.event
async def on_ready():
    precenseLoop.start()


@bot.event
async def setup_hook():
    if os.getenv("site_test") != "a":
        await bot.load_extension("cogs.link")
        await bot.load_extension("cogs.jihanki_edit")
        await bot.load_extension("cogs.jihanki_panel")
        await bot.load_extension("cogs.send_money")
        await bot.load_extension("cogs.claim_money")
        await bot.load_extension("cogs.help")
        await bot.load_extension("cogs.admin")
    await bot.load_extension("cogs.site")

    app.add_api_route(
        "/callback",
        bot.cogs.get("SiteCog").discordCallback,
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    app.add_api_route(
        "/mypage",
        bot.cogs.get("SiteCog").myPage,
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    app.add_api_route(
        "/logout", bot.cogs.get("SiteCog").logout, include_in_schema=False
    )
    app.add_api_route(
        "/api/bot",
        bot.cogs.get("SiteCog").getBotStatus,
    )
    app.add_api_route(
        "/api/payment/me",
        bot.cogs.get("SiteCog").getUserData,
    )
    app.add_api_route(
        "/api/payment/history",
        bot.cogs.get("SiteCog").getPaymentHistory,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database.connect()
    asyncio.create_task(bot.start(os.getenv("discord")))
    yield
    async with asyncio.timeout(60):
        await Database.pool.close()


app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)
templates = Jinja2Templates(directory="pages")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
