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

from .account import AccountManager, AccountNotLinkedException
from .database import Database

dotenv.load_dotenv()


class ServiceEnum(enum.Enum):
    NONE = "NONE"
    PAYPAY = "PAYPAY"
    KYASH = "KYASH"


def serviceString(service: ServiceEnum):
    match service:
        case ServiceEnum.NONE:
            return "決済無し"
        case ServiceEnum.PAYPAY:
            return "<a:paypay:1301478001430626348> PayPay"
        case ServiceEnum.KYASH:
            return "<a:kyash:1301478014600609832> Kyash"
        case _:
            return "不明"


class SendMoneyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipherSuite = Fernet(os.getenv("fernet_key").encode())

    @app_commands.command(name="sendmoney", description="ユーザーに送金します。")
    @app_commands.rename(service="サービス", amount="金額", user="送信先")
    @app_commands.describe(
        service="送金する際に使用するサービス",
        amount="送金する金額",
        user="送金先ユーザー",
    )
    @app_commands.choices(
        service=[
            app_commands.Choice(name="Kyash", value="kyash"),
            app_commands.Choice(name="PayPay", value="paypay"),
        ]
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def sendMoneyCommand(
        self,
        interaction: discord.Interaction,
        service: str,
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

        async def sendLog(service: ServiceEnum, errorText: str):
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
        if service == "kyash":
            try:
                ownerKyash: Kyash = await AccountManager.loginKyash(user.id)
            except AccountNotLinkedException:
                embed = discord.Embed(
                    title="送信先ユーザーがKyashのアカウントをリンクしていません",
                    description=f"{user.mention} さんに「PayPayのアカウントをリンクしてください！」と言ってあげてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="[サポートサーバー](https://discord.gg/2TfFUuY3RG) へ報告することができます。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                kyash: Kyash = await AccountManager.loginKyash(interaction.user.id)
            except AccountNotLinkedException:
                commands = await self.bot.tree.fetch_commands()
                for cmd in commands:
                    if cmd.name == "link":
                        commandId = cmd.id
                embed = discord.Embed(
                    title="Kyashのアカウントが紐づけされていません",
                    description=f"</link:{commandId}> コマンドを使用し、アカウントを紐づけしてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="[サポートサーバー](https://discord.gg/2TfFUuY3RG) へ報告することができます。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await kyash.get_wallet()
            except Exception as e:
                embed = discord.Embed(
                    title="エラーが発生しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            if kyash.all_balance < amount:
                embed = discord.Embed(
                    title="残高が足りません",
                    description="Kyashをチャージしてください",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await kyash.create_link(
                    amount=amount,
                    message="送ります！",
                    is_claim=False,
                )
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(sendLog(ServiceEnum.KYASH, traceback.format_exc()))
                embed = discord.Embed(
                    title="送金に失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await ownerKyash.link_check(kyash.created_link)

                await ownerKyash.link_recieve(kyash.created_link, ownerKyash.link_uuid)
            except Exception as e:
                traceback.print_exc()
                await kyash.link_cancel(kyash.created_link, ownerKyash.link_uuid)
                asyncio.create_task(sendLog(ServiceEnum.KYASH, traceback.format_exc()))
                embed = discord.Embed(
                    title="受け取り側が受け取りに失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            service = ServiceEnum.KYASH
        else:
            if not await AccountManager.paypayExists(user.id):
                embed = discord.Embed(
                    title="送信先ユーザーがPayPayのアカウントをリンクしていません",
                    description=f"{user.mention} さんに「PayPayのアカウントをリンクしてください！」と言ってあげてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                paypay: PayPay = await AccountManager.loginPayPay(interaction.user.id)
            except AccountNotLinkedException:
                commands = await self.bot.tree.fetch_commands()
                for cmd in commands:
                    if cmd.name == "link":
                        commandId = cmd.id
                embed = discord.Embed(
                    title="PayPayのアカウントが紐づけされていません",
                    description=f"</link:{commandId}> コマンドを使用し、アカウントを紐づけしてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="[サポートサーバー](https://discord.gg/2TfFUuY3RG) へ報告することができます。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await paypay.get_balance()
            except Exception as e:
                embed = discord.Embed(
                    title="エラーが発生しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            if (int(paypay.money or 0) + int(paypay.money_light or 0)) < amount:
                embed = discord.Embed(
                    title="残高が足りません",
                    description="PayPayをチャージしてください",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await paypay.send_money(
                    amount, AccountManager.paypayExternalUserIds[user.id]
                )
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(sendLog(ServiceEnum.PAYPAY, traceback.format_exc()))
                embed = discord.Embed(
                    title="送金に失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            service = ServiceEnum.PAYPAY

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
            "SEND_PAYPAY" if service == ServiceEnum.PAYPAY else "SEND_KYASH",
            -amount,
        )

        paymentId = next(gen)

        await Database.pool.execute(
            "INSERT INTO history (id, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5)",
            paymentId,
            user.id,
            interaction.user.id,
            "GOT_PAYPAY" if service == ServiceEnum.PAYPAY else "GOT_KYASH",
            amount,
        )

        embed = (
            discord.Embed(
                title="送金しました！",
                description="トラブルが発生した場合は[サポートサーバー](https://discord.gg/2TfFUuY3RG)までどうぞ",
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
