import os
import traceback
from typing import Literal, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dotenv
from aiokyasher import Kyash
from aiopaypaython import PayPay
from aiopaypaythonwebapi import PayPayWebAPI
from cryptography.fernet import Fernet

from .database import Database

dotenv.load_dotenv()


class AccountNotLinkedException(Exception):
    """アカウントがリンクされていない"""

    pass


class FailedToLoginException(Exception):
    """ログインに失敗した"""

    pass


class AccountService:
    kyashCache: dict[int, Kyash] = {}
    paypayCache: dict[int, PayPay] = {}
    paypayWebAPICache: dict[int, PayPayWebAPI] = {}
    paypayExternalUserIds: dict[int, str] = {}
    cipherSuite = Fernet(os.getenv("fernet_key").encode())

    @classmethod
    async def paypayExists(cls, userId: int) -> bool:
        if userId in cls.paypayCache:
            return True
        else:
            paypayAccount = await Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", userId
            )
            if not paypayAccount:
                return False
            if not paypayAccount["client_uuid"]:
                return False
            cls.paypayExternalUserIds[userId] = paypayAccount["external_user_id"]
            return True

    @classmethod
    async def paypayWebAPIExists(cls, userId: int) -> bool:
        if userId in cls.paypayCache:
            return True
        else:
            paypayAccount = await Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", userId
            )
            if not paypayAccount:
                return False
            if not paypayAccount["webapi_client_uuid"]:
                return False
            return True

    @classmethod
    async def kyashExists(cls, userId: int) -> bool:
        if userId in cls.paypayCache:
            return True
        else:
            kyashAccount = await Database.pool.fetchrow(
                "SELECT * FROM kyash WHERE id = $1", userId
            )
            if not kyashAccount:
                return False
            return True

    @classmethod
    async def getProxy(
        cls, userId: int, service: Literal["kyash", "paypay"]
    ) -> Optional[str]:
        account = await Database.pool.fetchrow(
            f"SELECT * FROM {service} WHERE id = $1", userId
        )
        if not account:
            raise AccountNotLinkedException()
        return account["proxy"]

    @classmethod
    async def loginPayPayProcess(cls, userId: int) -> PayPay:
        paypayAccount = await Database.pool.fetchrow(
            "SELECT * FROM paypay WHERE id = $1", userId
        )
        if not paypayAccount:
            raise AccountNotLinkedException()

        cls.paypayExternalUserIds[userId] = paypayAccount["external_user_id"]

        paypay = PayPay(proxy=paypayAccount["proxy"])
        await paypay.initialize(
            access_token=cls.cipherSuite.decrypt(paypayAccount["access_token"]).decode()
        )

        async def tokenRefresh():
            await paypay.token_refresh(
                cls.cipherSuite.decrypt(paypayAccount["refresh_token"]).decode()
            )
            expiresAt = datetime.now(ZoneInfo("Asia/Tokyo")) + timedelta(days=90)
            await Database.pool.execute(
                "UPDATE ONLY paypay SET access_token = $1, refresh_token = $2, expires_at = $3 WHERE id = $4",
                paypay.access_token,
                paypay.refresh_token,
                expiresAt,
                userId,
            )

        if (
            paypayAccount["expires_at"].timestamp()
            <= datetime.now(ZoneInfo("Asia/Tokyo")).timestamp()
        ):
            await tokenRefresh()

        try:
            await paypay.get_balance()
        except:
            try:
                await tokenRefresh()
            except:
                if (
                    paypayAccount["device_uuid"]
                    and paypayAccount["client_uuid"]
                    and paypayAccount["phone"]
                    and paypayAccount["password"]
                ):
                    try:
                        paypay = PayPay(proxy=paypayAccount["proxy"])
                        await paypay.initialize(
                            phone=cls.cipherSuite.decrypt(
                                paypayAccount["phone"]
                            ).decode(),
                            password=cls.cipherSuite.decrypt(
                                paypayAccount["password"]
                            ).decode(),
                            device_uuid=str(paypayAccount["device_uuid"]).upper(),
                            client_uuid=str(paypayAccount["client_uuid"]).upper(),
                        )
                        expiresAt = datetime.now(ZoneInfo("Asia/Tokyo")) + timedelta(
                            days=90
                        )

                        await Database.pool.execute(
                            "UPDATE ONLY paypay SET access_token = $1, refresh_token = $2, expires_at = $3 WHERE id = $4",
                            paypay.access_token,
                            paypay.refresh_token,
                            expiresAt,
                            userId,
                        )
                    except:
                        raise FailedToLoginException()
                else:
                    raise FailedToLoginException()
        cls.paypayCache[userId] = paypay
        return paypay

    @classmethod
    async def loginPayPay(cls, userId: int) -> PayPay:
        if userId in cls.paypayCache:
            paypay = cls.paypayCache[userId]
            try:
                await paypay.get_balance()
                return paypay
            except:
                return await cls.loginPayPayProcess(userId)
        else:
            return await cls.loginPayPayProcess(userId)

    @classmethod
    async def loginPayPayWebAPIProcess(cls, userId: int) -> PayPay:
        paypayAccount = await Database.pool.fetchrow(
            "SELECT * FROM paypay WHERE id = $1", userId
        )
        if not paypayAccount:
            raise AccountNotLinkedException()
        if not paypayAccount["webapi_client_uuid"]:
            raise AccountNotLinkedException()
        paypay = PayPayWebAPI(proxy=paypayAccount["proxy"])

        async def reLogin():
            await paypay.initialize(
                phone=cls.cipherSuite.decrypt(paypayAccount["phone"]).decode(),
                password=cls.cipherSuite.decrypt(paypayAccount["password"]).decode(),
                client_uuid=str(paypayAccount["webapi_client_uuid"]).upper(),
            )

            await Database.pool.execute(
                "UPDATE ONLY paypay SET webapi_access_token = $1 WHERE id = $2",
                paypay.access_token,
                userId,
            )

        if (
            paypayAccount["webapi_expires_at"].timestamp()
            <= datetime.now(ZoneInfo("Asia/Tokyo")).timestamp()
        ):
            try:
                await reLogin()
            except:
                raise FailedToLoginException()
        else:
            try:
                await paypay.initialize(
                    access_token=cls.cipherSuite.decrypt(
                        paypayAccount["webapi_access_token"]
                    ).decode()
                )
                await paypay.get_balance()
            except:
                try:
                    await reLogin()
                except:
                    raise FailedToLoginException()
        cls.paypayWebAPICache[userId] = paypay
        return paypay

    @classmethod
    async def loginPayPayWebAPI(cls, userId: int) -> PayPayWebAPI:
        if userId in cls.paypayWebAPICache:
            paypay = cls.paypayWebAPICache[userId]
            try:
                await paypay.get_balance()
                return paypay
            except:
                return await cls.loginPayPayWebAPIProcess(userId)
        else:
            return await cls.loginPayPayWebAPIProcess(userId)

    @classmethod
    async def loginKyashProcess(cls, userId) -> Kyash:
        kyashAccount = await Database.pool.fetchrow(
            "SELECT * FROM kyash WHERE id = $1", userId
        )
        if not kyashAccount:
            raise AccountNotLinkedException()

        kyash = Kyash(proxy=kyashAccount["proxy"])
        try:
            await kyash.login(
                email=cls.cipherSuite.decrypt(kyashAccount["email"]).decode(),
                password=cls.cipherSuite.decrypt(kyashAccount["password"]).decode(),
                client_uuid=str(kyashAccount["client_uuid"]),
                installation_uuid=str(kyashAccount["installation_uuid"]),
            )
        except:
            raise FailedToLoginException()
        cls.kyashCache[userId] = kyash
        return kyash

    @classmethod
    async def loginKyash(cls, userId: int) -> Kyash:
        if userId in cls.kyashCache:
            return cls.kyashCache[userId]
        else:
            return await cls.loginKyashProcess(userId)
