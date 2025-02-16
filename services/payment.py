import discord

from .account import AccountService


class PaymentService:
    """
    決済系のサービス
    """

    @classmethod
    async def payWithPayPay(
        self, *, amount: int, buyer: discord.Member, seller: discord.Member
    ):
        pass
