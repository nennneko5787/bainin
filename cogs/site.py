import os
import traceback
import math

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


async def loadUserData(data: str = Cookie(None)):
    if not data:
        return None
    data: dict = orjson.loads(cipherSuite.decrypt(data.encode()))
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

    async def logout(self, userData: dict = Depends(loadUserData)):
        if not userData:
            raise HTTPException(401)

        response = RedirectResponse("/")
        response.set_cookie(
            "data",
            "",
            max_age=-1,
        )
        return response

    async def getBotStatus(self):
        """ボットのステータスを取得します。現時点ではカスなレスポンスが返ります。"""

        appInfo = await self.bot.application_info()
        return {
            "status": f"{len(self.bot.guilds)}サーバーと{appInfo.approximate_user_install_count}ユーザーが利用中<br>{await Database.pool.fetchval('SELECT COUNT(*) FROM jihanki')}台の自販機が作成されました",
        }

    async def getUserData(self, userData: dict = Depends(loadUserData)):
        """ユーザーのデータを取得します。"""
        if not userData:
            raise HTTPException(401)

        return userData

    async def getPaymentHistory(
        self, userData: dict = Depends(loadUserData), page: int = 0
    ):
        """ユーザーの購入履歴を取得します。"""
        limit: int = 30

        if not userData:
            raise HTTPException(401)

        count = await Database.pool.fetchval(
            "SELECT COUNT(*) FROM history WHERE user_id = $1", int(userData["id"])
        )

        histories = []

        for history in await Database.pool.fetch(
            "SELECT * FROM history WHERE user_id = $1 ORDER BY bought_at DESC OFFSET $2 LIMIT $3",
            int(userData["id"]),
            page * limit,
            limit,
        ):
            history = dict(history)
            history["id_str"] = str(history["id"])
            if history["jihanki"]:
                history["jihanki"] = orjson.loads(history["jihanki"])
            if history["good"]:
                history["good"] = orjson.loads(history["good"])
            user = await self.bot.fetch_user(history["to_id"])
            history["to"] = f"{user.display_name} (ID: {user.name})"
            histories.append(history)

        data = {
            "total": count,
            "pages": math.ceil(count / limit),
            "histories": histories,
        }

        return data

    async def getPayment(self, paymentId: int, userData: dict = Depends(loadUserData)):
        """ユーザーの購入履歴の詳細を取得します。"""
        if not userData:
            raise HTTPException(401)

        payment = await Database.pool.fetchrow(
            "SELECT * FROM history WHERE id = $1", paymentId
        )

        if not payment:
            raise HTTPException(404)

        if payment["user_id"] != int(userData["id"]):
            raise HTTPException(403)

        payment = dict(payment)

        payment["id_str"] = str(payment["id"])

        if payment["jihanki"]:
            payment["jihanki"] = orjson.loads(payment["jihanki"])
        if payment["good"]:
            payment["good"] = orjson.loads(payment["good"])
            payment["good"]["value"] = cipherSuite.decrypt(
                payment["good"]["value"].encode()
            ).decode()
        user = await self.bot.fetch_user(payment["to_id"])
        payment["to"] = f"{user.display_name} (ID: {user.name})"

        return payment

    async def myPage(self, request: Request, userData: dict = Depends(loadUserData)):
        if not userData:
            return RedirectResponse(
                "https://discord.com/oauth2/authorize?client_id=1289535525681627156&response_type=code&redirect_uri=http%3A%2F%2Fbainin.nennneko5787.net%2Fcallback&scope=identify"
            )
        return templates.TemplateResponse(request, "mypage.html")


async def setup(bot: commands.Bot):
    await bot.add_cog(SiteCog(bot))
