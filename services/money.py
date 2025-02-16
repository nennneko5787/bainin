from typing import Union

import discord

from objects import PaymentType
from services.account import AccountService


class PayPayAccountNotExists(Exception):
    pass


class MoneyService:
    @classmethod
    async def sendMoneyWithPayPay(
        cls,
        *,
        amount: int,
        target: Union[discord.User, discord.Member],
        to: Union[discord.User, discord.Member],
    ) -> bool:
        if not await AccountService.paypayExists(target.id):
            raise PayPayAccountNotExists("PayPayアカウントをリンクしてください")
        if not await AccountService.paypayExists(to.id):
            raise PayPayAccountNotExists(
                "送金先ユーザーにPayPayアカウントをリンクするようにお願いしてください"
            )
        targetPayPayAccount = await AccountService.loginPayPay(target.id)
        toPayPayExternalId = AccountService.paypayExternalUserIds[to.id]

        await targetPayPayAccount.send_money(amount, toPayPayExternalId)
        return True

    @classmethod
    async def sendMoneyWithKyash(
        cls,
        *,
        amount: int,
        target: Union[discord.User, discord.Member],
        to: Union[discord.User, discord.Member],
    ) -> bool:
        if not await AccountService.kyashExists(target.id):
            raise PayPayAccountNotExists("PayPayアカウントをリンクしてください")
        if not await AccountService.kyashExists(to.id):
            raise PayPayAccountNotExists(
                "送金先ユーザーにPayPayアカウントをリンクするようにお願いしてください"
            )
        targetKyashAccount = await AccountService.loginKyash(target.id)
        toKyashAccount = await AccountService.loginKyash(to.id)

        await targetKyashAccount.create_link(amount)
        url = targetKyashAccount.created_link
        await toKyashAccount.link_recieve(url)
        return True

    @classmethod
    async def sendMoney(
        cls,
        *,
        amount: int,
        target: Union[discord.User, discord.Member],
        to: Union[discord.User, discord.Member],
        type: PaymentType,
    ) -> bool:
        if amount <= 0:
            raise ValueError("amountは1以上でなければなりません")

        match (type):
            case PaymentType.PAYPAY:
                return await cls.sendMoneyWithPayPay(
                    amount=amount, target=target, to=to
                )
            case PaymentType.KYASH:
                return await cls.sendMoneyWithKyash(amount=amount, target=target, to=to)
            case _:
                raise ValueError("PaymentTypeが無効です")
