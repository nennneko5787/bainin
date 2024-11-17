import os
import traceback

import dotenv
import httpx
import discord
import orjson
from discord.ext import commands
from cryptography.fernet import Fernet
from fastapi import Request, Depends, Cookie, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .database import Database

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())

templates = Jinja2Templates(directory="pages")


async def loadUserData(request: Request, data: str = Cookie(...)):
    data: dict = orjson.loads(cipherSuite.decrypt(data.encode()))
    if data.get("ipaddr") != request.client.host:
        raise HTTPException(status_code=401)
    return data


class SiteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = httpx.AsyncClient()

    async def discordCallback(self, request: Request, code: str):
        try:
            response = await self.client.post(
                "https://discord.com/api/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": os.getenv("oauth2_client_id"),
                    "client_secret": os.getenv("oauth2_secret"),
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": os.getenv("redirect_uri"),
                },
            )
            if response.status_code != 200:
                return templates.TemplateResponse(
                    request=request,
                    name="auth_error.html",
                    context={
                        "message": f"oauth2の検証に失敗しました。code: {response.status_code}"
                    },
                    status_code=403,
                )
            accessTokenResponse = response.json()
            print(accessTokenResponse)
            if "identify" in accessTokenResponse["scope"]:
                accessToken = accessTokenResponse["access_token"]

                response = await self.client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bearer {accessToken}"},
                )
                if response.status_code != 200:
                    return templates.TemplateResponse(
                        request=request,
                        name="auth_error.html",
                        context={
                            "message": f"ユーザーデータの取得に失敗しました。code: {response.status_code}"
                        },
                        status_code=403,
                    )
                userData = response.json()
                userData["ipaddr"] = request.client.host

                response = RedirectResponse("/mypage")
                response.set_cookie(
                    "data",
                    cipherSuite.encrypt(orjson.dumps(userData)).decode(),
                    max_age=60 * 60 * 60 * 24 * 365,
                )
                return response
            else:
                raise HTTPException(status_code=403)
        except Exception as e:
            traceback.print_exc()
            return templates.TemplateResponse(
                request=request,
                name="auth_error.html",
                context={"message": str(e)},
            )

    async def getBotStatus(self):
        appInfo = await self.bot.application_info()
        return {
            "guildsCount": len(self.bot.guilds),
            "usersCount": appInfo.approximate_user_install_count,
        }

    async def getPaymentHistory(self, userData: dict = Depends(loadUserData)):
        histories = [
            dict(history)
            for history in await Database.pool.fetch(
                "SELECT * FROM history WHERE user_id = $1", int(userData["id"])
            )
        ]

        return histories


async def setup(bot: commands.Bot):
    await bot.add_cog(SiteCog(bot))
