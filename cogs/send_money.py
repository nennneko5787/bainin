import enum
import asyncio
import os
import traceback

import aiohttp
import discord
import dotenv
from discord.ext import commands
from discord import app_commands
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet

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

    @app_commands.command(name="remittance", description="ユーザーに送金します。")
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
    async def remittanceCommand(
        self,
        interaction: discord.Interaction,
        service: str,
        amount: app_commands.Range[int, 1],
        user: discord.User,
    ):
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
            ownerKyashAccount = await Database.pool.fetchrow(
                "SELECT * FROM kyash WHERE id = $1", user.id
            )
            if not ownerKyashAccount:
                embed = discord.Embed(
                    title="送信先ユーザーがKyashのアカウントをリンクしていません",
                    description=f"{user.mention} さんに「PayPayのアカウントをリンクしてください！」と言ってあげてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            kyashAccount = await Database.pool.fetchrow(
                "SELECT * FROM kyash WHERE id = $1", interaction.user.id
            )
            if not kyashAccount:
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
            ownerKyash = Kyash()
            try:
                await ownerKyash.login(
                    email=self.cipherSuite.decrypt(ownerKyashAccount["email"]).decode(),
                    password=self.cipherSuite.decrypt(
                        ownerKyashAccount["password"]
                    ).decode(),
                    client_uuid=str(ownerKyashAccount["client_uuid"]),
                    installation_uuid=str(ownerKyashAccount["installation_uuid"]),
                )
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(ServiceEnum.KYASH, sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="Kyashでのログインに失敗しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            kyash = Kyash()
            try:
                await kyash.login(
                    email=self.cipherSuite.decrypt(kyashAccount["email"]).decode(),
                    password=self.cipherSuite.decrypt(
                        kyashAccount["password"]
                    ).decode(),
                    client_uuid=str(kyashAccount["client_uuid"]),
                    installation_uuid=str(kyashAccount["installation_uuid"]),
                )
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(ServiceEnum.KYASH, sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="Kyashでのログインに失敗しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            await kyash.get_wallet()
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
                asyncio.create_task(ServiceEnum.KYASH, sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="送金に失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await ownerKyash.link_recieve(url=kyash.created_link)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(ServiceEnum.KYASH, sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="オーナー側の受け取りに失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            service = ServiceEnum.KYASH
        else:
            ownerPaypayAccount = await Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", user.id
            )
            if not ownerPaypayAccount:
                embed = discord.Embed(
                    title="送信先ユーザーがPayPayのアカウントをリンクしていません",
                    description=f"{user.mention} さんに「PayPayのアカウントをリンクしてください！」と言ってあげてください。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            paypayAccount = await Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", interaction.user.id
            )
            if not paypayAccount:
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

            paypay = PayPay()
            try:
                await paypay.initialize(
                    access_token=self.cipherSuite.decrypt(
                        paypayAccount["access_token"]
                    ).decode()
                )
            except:
                try:
                    await paypay.token_refresh(
                        self.cipherSuite.decrypt(
                            paypayAccount["refresh_token"]
                        ).decode()
                    )
                except Exception as e:
                    traceback.print_exc()
                    asyncio.create_task(
                        ServiceEnum.PAYPAY, sendLog(traceback.format_exc())
                    )
                    embed = discord.Embed(
                        title="PayPayでのログインに失敗しました。",
                        description=str(e),
                        colour=discord.Colour.red(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

            await paypay.get_balance()
            if (paypay.money + paypay.money_light) < amount:
                embed = discord.Embed(
                    title="残高が足りません",
                    description="PayPayをチャージしてください",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await paypay.send_money(amount, ownerPaypayAccount["external_user_id"])
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(ServiceEnum.PAYPAY, sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="送金に失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            service = ServiceEnum.PAYPAY

        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(
                os.getenv("money_webhook"), session=session
            )

            embed = (
                discord.Embed(title="送金されました", colour=discord.Colour.green())
                .set_thumbnail(url=interaction.user.display_avatar.url)
                .add_field(
                    name="送金元ユーザー",
                    value=f"{interaction.user.mention} (ID: `{interaction.user.name}`) (UID: {interaction.user.id})",
                )
                .add_field(
                    name="送金先ユーザー",
                    value=f"{user.mention} (ID: `{user.name}`) (UID: {user.id})",
                )
                .add_field(name="金額", value=f"{amount}円")
                .add_field(
                    name="種別",
                    value=serviceString(service),
                )
            )

            await webhook.send(embed=embed)

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

        embed = (
            discord.Embed(
                title="送金しました！",
                description="相手の方にDMが送信されていると思うので、トラブルになったらボット制作者の`nennneko5787`まで言ってくれればサポートします",
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
