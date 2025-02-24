import asyncio
import enum
import os
import traceback

import aiohttp
import discord
import dotenv
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands
from snowflake import SnowflakeGenerator

from services.database import Database
from services.money import MoneyService
from objects import PaymentType

dotenv.load_dotenv()


def serviceString(service: PaymentType):
    match service:
        case PaymentType.NONE:
            return "決済無し"
        case PaymentType.PAYPAY:
            return "<a:paypay:1301478001430626348> PayPay"
        case PaymentType.KYASH:
            return "<a:kyash:1301478014600609832> Kyash"
        case _:
            return "不明"


moneyGroup = app_commands.Group(
    name="money",
    description="自販機関連のコマンド。",
    allowed_contexts=app_commands.AppCommandContext(
        guild=True, dm_channel=True, private_channel=True
    ),
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
)


class SendMoneyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipherSuite = Fernet(os.getenv("fernet_key").encode())

    # @moneyGroup.command(name="send", description="ユーザーに送金します。")
    @app_commands.command(name="sendmoney", description="ユーザーに送金します。")
    @app_commands.rename(_service="サービス", amount="金額", user="送信先")
    @app_commands.describe(
        _service="送金する際に使用するサービス",
        amount="送金する金額",
        user="送金先ユーザー",
    )
    @app_commands.choices(
        _service=[
            app_commands.Choice(name="Kyash", value="KYASH"),
            app_commands.Choice(name="PayPay", value="PAYPAY"),
        ]
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def sendMoneyCommand(
        self,
        interaction: discord.Interaction,
        _service: str,
        amount: app_commands.Range[int, 1],
        user: discord.User,
    ):
        if user.bot:
            embed = discord.Embed(
                title="エラーが発生しました",
                description="ボットへは送金できません",
                colour=discord.Colour.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        if user.id == interaction.user.id:
            embed = discord.Embed(
                title="自分自身には送金できません", colour=discord.Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        async def sendLog(service: PaymentType, errorText: str):
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(
                    os.getenv("error_webhook"), session=session
                )

                embed = (
                    discord.Embed(
                        title="エラーが発生しました",
                        colour=discord.Colour.red(),
                    )
                    .set_thumbnail(url=interaction.user.display_avatar.url)
                    .add_field(
                        name="送信先ユーザー",
                        value=f"{user.display_name} (ID: `{user.name}`) (UID: `{user.id}`)",
                    )
                    .add_field(
                        name="送信元ユーザー",
                        value=f"{interaction.user.mention} (ID: `{interaction.user.name}`) (UID: `{interaction.user.id}`)",
                    )
                    .add_field(
                        name="種別",
                        value=serviceString(service),
                    )
                    .add_field(
                        name="エラー",
                        value=f"```\n{errorText}```\n",
                    )
                )

                await webhook.send(embed=embed)

        await interaction.response.defer(ephemeral=True)
        service = PaymentType(_service.value)
        try:
            await MoneyService.sendMoney(
                amount=amount, target=interaction.user, to=user
            )
        except:
            await sendLog(service, traceback.format_exc())

        try:
            embed = (
                discord.Embed(
                    title="送金してもらいました！",
                    colour=discord.Colour.green(),
                )
                .set_thumbnail(url=interaction.user.display_avatar)
                .add_field(
                    name="誰から",
                    value=f"{interaction.user.mention} (`{interaction.user.display_name}`) (ID: `{interaction.user.name}`)",
                )
                .add_field(name="どれぐらい", value=f"{amount}円")
                .add_field(name="何で", value=serviceString(service))
            )
            await user.send(embed=embed)
        except:
            pass

        try:
            embed = (
                discord.Embed(
                    title="送金ログ",
                    colour=discord.Colour.green(),
                )
                .set_thumbnail(url=user.display_avatar)
                .add_field(
                    name="誰に",
                    value=f"{user.mention} (`{user.display_name}`) (ID: `{user.name}`)",
                )
                .add_field(name="どれぐらい", value=f"{amount}円")
                .add_field(name="何で", value=serviceString(service))
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass

        gen = SnowflakeGenerator(15)
        paymentId = next(gen)

        await Database.pool.execute(
            "INSERT INTO history (id, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5)",
            paymentId,
            interaction.user.id,
            user.id,
            "SEND_PAYPAY" if service == PaymentType.PAYPAY else "SEND_KYASH",
            -amount,
        )

        paymentId = next(gen)

        await Database.pool.execute(
            "INSERT INTO history (id, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5)",
            paymentId,
            user.id,
            interaction.user.id,
            "GOT_PAYPAY" if service == PaymentType.PAYPAY else "GOT_KYASH",
            amount,
        )

        embed = (
            discord.Embed(
                title="送金しました！",
                description="トラブルが発生した場合は[サポートサーバー](https://discord.gg/PN3KWEnYzX)までどうぞ",
                colour=discord.Colour.green(),
            )
            .set_thumbnail(url=user.display_avatar)
            .add_field(
                name="誰に",
                value=f"{user.mention} (`{user.display_name}`) (ID: `{user.name}`)",
            )
            .add_field(name="どれぐらい", value=f"{amount}円")
            .add_field(name="何で", value=serviceString(service))
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SendMoneyCog(bot))
