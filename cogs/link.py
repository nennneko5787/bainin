import asyncio
import os
import traceback

import discord
import dotenv
from discord.ext import commands
from discord import app_commands
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet

from .database import Database

dotenv.load_dotenv()


class AccountLinkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipherSuite = Fernet(os.getenv("fernet_key").encode())

    @app_commands.command(
        name="check", description="KyashやPayPayのアカウントの情報を確認します。"
    )
    @app_commands.choices(
        service=[
            app_commands.Choice(name="Kyash", value="kyash"),
            app_commands.Choice(name="PayPay", value="paypay"),
        ]
    )
    @app_commands.describe(service="確認したいサービス")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def checkCommand(
        self,
        interaction: discord.Interaction,
        service: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if service == "kyash":
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
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="Kyashでのログインに失敗しました。",
                    description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            await kyash.get_profile()
            await kyash.get_wallet()
            embed = (
                discord.Embed(title="Kyashの情報", colour=discord.Colour.blue())
                .set_author(name=kyash.username, icon_url=kyash.icon)
                .add_field(name="すべての残高", value=kyash.all_balance)
                .add_field(name="所持しているKyashマネー", value=kyash.money)
                .add_field(name="所持しているKyashバリュー", value=kyash.value)
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
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
                pass
                traceback.print_exc()
                try:
                    await paypay.token_refresh(
                        self.cipherSuite.decrypt(
                            paypayAccount["refresh_token"]
                        ).decode()
                    )
                except:
                    traceback.print_exc()
                    embed = discord.Embed(
                        title="PayPayでのログインに失敗しました。",
                        description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                        colour=discord.Colour.red(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            await paypay.get_profile()
            await paypay.get_balance()
            embed = (
                discord.Embed(title="PayPayの情報", colour=discord.Colour.red())
                .set_author(name=paypay.name, icon_url=paypay.icon)
                .add_field(name="すべての残高", value=paypay.all_balance)
                .add_field(name="すべての利用可能な残高", value=paypay.useable_balance)
                .add_field(
                    name="自販機で利用可能な残高",
                    value=(paypay.money + paypay.money_light),
                )
                .add_field(name="所持しているPayPayマネー", value=paypay.money)
                .add_field(
                    name="所持しているPayPayマネーライト", value=paypay.money_light
                )
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="proxy",
        description="使用するプロキシを変更することができます。",
    )
    @app_commands.describe(
        service="プロキシを変更したいサービス",
        proxy="アクセスするために使用するプロキシ。",
    )
    @app_commands.choices(
        service=[
            app_commands.Choice(name="Kyash", value="kyash"),
            app_commands.Choice(name="PayPay", value="paypay"),
        ]
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def proxyCommand(
        self, interaction: discord.Interaction, service: str, proxy: str
    ):
        await interaction.response.defer(ephemeral=True)
        if service == "kyash":
            row = Database.pool.fetchrow(
                "SELECT * FROM kyash WHERE id = $1", interaction.user.id
            )
            if not row:
                embed = discord.Embed(
                    title="まだアカウントリンクしていません",
                    description="`/link` コマンドを使用してアカウントをリンクしてください",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            await Database.pool.execute(
                "UPDATE ONLY kyash SET proxy = $1 WHERE id = $2",
                proxy,
                interaction.user.id,
            )

            embed = discord.Embed(
                title="プロキシを変更しました", colour=discord.Colour.green()
            )
            await interaction.followup.send(embed=embed)
        else:
            row = Database.pool.fetchrow(
                "SELECT * FROM paypay WHERE id = $1", interaction.user.id
            )
            if not row:
                embed = discord.Embed(
                    title="まだアカウントリンクしていません",
                    description="`/link` コマンドを使用してアカウントをリンクしてください",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            await Database.pool.execute(
                "UPDATE ONLY paypay SET proxy = $1 WHERE id = $2",
                proxy,
                interaction.user.id,
            )

            embed = discord.Embed(
                title="プロキシを変更しました", colour=discord.Colour.green()
            )
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="link",
        description="KyashやPayPayのアカウントとリンクします。アカウント変更もこっち",
    )
    @app_commands.describe(
        service="リンクしたいサービス",
        credential="Kyashの場合はメールアドレスです。PayPayの場合は電話番号です。",
        password="ログインするために使用するパスワード。",
        proxy="アクセスするために使用するプロキシ。",
    )
    @app_commands.choices(
        service=[
            app_commands.Choice(name="Kyash", value="kyash"),
            app_commands.Choice(name="PayPay", value="paypay"),
        ]
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def linkCommand(
        self,
        interaction: discord.Interaction,
        service: str,
        credential: str,
        password: str,
        proxy: str = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if service == "kyash":
            if proxy:
                proxies = {
                    "http": proxy,
                    "https": proxy,
                }
            else:
                proxies = None

            kyash = Kyash(proxy=proxies)
            try:
                await kyash.login(credential, password)
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "ログインに失敗しました。", ephemeral=True
                )
                return

            await interaction.user.create_dm()

            await interaction.followup.send(
                "**2分以内**に、SMSに届いた**4桁の番号のみ**を**このボットのダイレクトメッセージ**へ送信してください。",
                ephemeral=True,
            )

            def check(m: discord.Message) -> bool:
                if m.channel.id == interaction.user.dm_channel.id:
                    return True
                else:
                    return False

            try:
                message = await self.bot.wait_for("message", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    "タイムアウトしました。", ephemeral=True
                )
                return
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "エラーが発生しました。", ephemeral=True
                )

            try:
                await kyash.validate_otp(message.content)
            except:
                traceback.print_exc()
                await message.reply("OTPの検証に失敗しました。")

            await Database.pool.execute(
                """
                    INSERT INTO kyash (id, email, password, client_uuid, installation_uuid)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        email = EXCLUDED.email,
                        password = EXCLUDED.password,
                        client_uuid = EXCLUDED.client_uuid,
                        installation_uuid = EXCLUDED.installation_uuid
                """,
                interaction.user.id,
                self.cipherSuite.encrypt(kyash.email.encode()).decode(),
                self.cipherSuite.encrypt(kyash.password.encode()).decode(),
                kyash.client_uuid,
                kyash.installation_uuid,
            )
            await message.reply(f"アカウントをリンクしました。")
        else:
            if proxy:
                proxies = {
                    "http": proxy,
                    "https": proxy,
                }
            else:
                proxies = None

            paypay = PayPay(proxies=proxies)
            try:
                await paypay.initialize(credential, password)
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "ログインに失敗しました。", ephemeral=True
                )
                return

            await interaction.user.create_dm()

            await interaction.followup.send(
                "**2分以内**に、SMSに届いた**URLのみ**を**このボットのダイレクトメッセージ**へ送信してください。",
                ephemeral=True,
            )

            def check(m: discord.Message) -> bool:
                if m.channel.id == interaction.user.dm_channel.id:
                    return True
                else:
                    return False

            try:
                message = await self.bot.wait_for("message", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    "タイムアウトしました。", ephemeral=True
                )
                return
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "エラーが発生しました。", ephemeral=True
                )

            try:
                await paypay.login(message.content)
            except:
                traceback.print_exc()
                await message.reply("OTPの検証に失敗しました。")

            await paypay.get_profile()

            await Database.pool.execute(
                """
                    INSERT INTO paypay (id, external_user_id, access_token, refresh_token)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        external_user_id = EXCLUDED.external_user_id,
                        access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token
                """,
                interaction.user.id,
                paypay.external_user_id,
                self.cipherSuite.encrypt(paypay.access_token.encode()).decode(),
                self.cipherSuite.encrypt(paypay.refresh_token.encode()).decode(),
            )
            await message.reply(f"アカウントをリンクしました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(AccountLinkCog(bot))
