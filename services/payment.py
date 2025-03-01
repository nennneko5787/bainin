import discord

from .account import AccountService


class AccountNotLinked(Exception):
    pass


class MoneyNotEnough(Exception):
    pass


class PaymentService:
    """
    決済系のサービス
    """

    @classmethod
    async def payWithPayPay(
        self, *, amount: int, buyer: discord.Member, seller: discord.Member
    ):
        if (not await AccountService.paypayExists(buyer.id)) or (
            not await AccountService.paypayExists(seller.id)
        ):
            raise AccountNotLinked()

        buyerPayPayAccount = await AccountService.loginPayPay(buyer.id)

        balance = await buyerPayPayAccount.get_balance()
        if (int(balance.money) + int(balance.money_light)) < amount:
            raise MoneyNotEnough()

        await buyerPayPayAccount.send_money(
            amount, AccountService.paypayExternalUserIds[seller.id]
        )

    @classmethod
    async def receivePayPayUrl(
        self, *, url: str, amount: int, seller: discord.Member, passcode: str = None
    ):
        if not await AccountService.paypayWebAPIExists(seller.id):
            raise AccountNotLinked()

        sellerPayPayAccount = await AccountService.loginPayPayWebAPI(seller.id)
        linkInfo = await sellerPayPayAccount.link_check(url)
        if int(linkInfo.amount) < amount:
            raise MoneyNotEnough()

        await sellerPayPayAccount.link_receive(url, passcode)

    @classmethod
    async def payWithKyash(
        self, *, amount: int, buyer: discord.Member, seller: discord.Member
    ):
        if (not await AccountService.kyashExists(buyer.id)) or (
            not await AccountService.kyashExists(seller.id)
        ):
            raise AccountNotLinked()

        buyerKyashAccount = await AccountService.loginKyash(buyer.id)

        await buyerKyashAccount.get_wallet()
        if (int(buyerKyashAccount.money) + int(buyerKyashAccount.value)) < amount:
            raise MoneyNotEnough()

        await buyerKyashAccount.create_link(amount)
        remittanceUrl = buyerKyashAccount.created_link

        sellerKyashAccount = await AccountService.loginKyash(seller.id)
        await sellerKyashAccount.link_recieve(remittanceUrl)

    @classmethod
    async def receiveKyashUrl(self, *, url: str, amount: int, seller: discord.Member):
        if not await AccountService.kyashExists(seller.id):
            raise AccountNotLinked()

        sellerKyashAccount = await AccountService.loginKyash(seller.id)
        await sellerKyashAccount.link_check(url)
        if int(sellerKyashAccount.link_amount) < amount:
            raise MoneyNotEnough()

        await sellerKyashAccount.link_recieve(url, sellerKyashAccount.link_uuid)
