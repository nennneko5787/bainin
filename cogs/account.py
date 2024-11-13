import os
import traceback

import dotenv
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet

from .database import Database

dotenv.load_dotenv()


class AccountNotLinkedException(Exception):
    """アカウントがリンクされていない"""

    pass


class FailedToLoginException(Exception):
    """ログインに失敗した"""

    pass


class AccountManager:
    kyashCache: dict[int, Kyash] = {}
    paypayCache: dict[int, PayPay] = {}
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
                raise AccountNotLinkedException()
            cls.paypayExternalUserIds[userId] = paypayAccount["external_user_id"]
            return True

    @classmethod
    async def loginPayPay(cls, userId: int) -> PayPay:
        if userId in cls.paypayCache:
            return cls.paypayCache[userId]
        else:
            paypayAccount = await Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", userId
            )
            if not paypayAccount:
                raise AccountNotLinkedException()

            if paypayAccount["proxy"]:
                proxies = {
                    "http": paypayAccount["proxy"],
                    "https": paypayAccount["proxy"],
                }
            else:
                proxies = None

            cls.paypayExternalUserIds[userId] = paypayAccount["external_user_id"]

            paypay = PayPay(proxies=proxies)
            try:
                await paypay.initialize(
                    access_token=cls.cipherSuite.decrypt(
                        paypayAccount["access_token"]
                    ).decode()
                )
            except:
                try:
                    paypay = PayPay(proxies=proxies)
                    await paypay.token_refresh(
                        cls.cipherSuite.decrypt(paypayAccount["refresh_token"]).decode()
                    )
                except:
                    raise FailedToLoginException()
            cls.paypayCache[userId] = paypay
            return paypay

    @classmethod
    async def loginKyash(cls, userId: int) -> Kyash:
        if userId in cls.kyashCache:
            return cls.kyashCache[userId]
        else:
            kyashAccount = await Database.pool.fetchrow(
                "SELECT * FROM kyash WHERE id = $1", userId
            )
            if not kyashAccount:
                raise AccountNotLinkedException()

            if kyashAccount["proxy"]:
                proxies = {
                    "http": kyashAccount["proxy"],
                    "https": kyashAccount["proxy"],
                }
            else:
                proxies = None

            kyash = Kyash(proxy=proxies)
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
