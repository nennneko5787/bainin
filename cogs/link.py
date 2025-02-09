import asyncio
import os
import traceback

import discord
import dotenv
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands

from .account import AccountManager, AccountNotLinkedException, FailedToLoginException
from .database import Database

dotenv.load_dotenv()


class AccountLinkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipherSuite = Fernet(os.getenv("fernet_key").encode())

    @app_commands.command(
        name="check", description="KyashやPayPayのアカウントの情報を確認します。"
    )
    @app_commands.rename(service="サービス")
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
            try:
                kyash: Kyash = await AccountManager.loginKyash(interaction.user.id)

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
            except FailedToLoginException:
                traceback.print_exc()
                embed = discord.Embed(
                    title="Kyashでのログインに失敗しました。",
                    description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="不明なエラーが発生しました",
                    description="[サポートサーバー](https://discord.gg/2TfFUuY3RG) へ報告することができます。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        else:
            try:
                paypay: PayPay = await AccountManager.loginPayPay(interaction.user.id)
                await paypay.get_profile()
                await paypay.get_balance()
                embed = (
                    discord.Embed(title="PayPayの情報", colour=discord.Colour.red())
                    .set_author(name=paypay.name, icon_url=paypay.icon)
                    .add_field(name="すべての残高", value=paypay.all_balance)
                    .add_field(
                        name="すべての利用可能な残高", value=paypay.useable_balance
                    )
                    .add_field(
                        name="自販機で利用可能な残高",
                        value=((paypay.money or 0) + (paypay.money_light or 0)),
                    )
                    .add_field(name="所持しているPayPayマネー", value=paypay.money)
                    .add_field(
                        name="所持しているPayPayマネーライト", value=paypay.money_light
                    )
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
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
            except FailedToLoginException:
                traceback.print_exc()
                embed = discord.Embed(
                    title="PayPayでのログインに失敗しました。",
                    description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except:
                traceback.print_exc()
                embed = discord.Embed(
                    title="不明なエラーが発生しました",
                    description="[サポートサーバー](https://discord.gg/2TfFUuY3RG) へ報告することができます。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

    @app_commands.command(
        name="proxy",
        description="使用するプロキシを変更することができます。",
    )
    @app_commands.rename(service="サービス", proxy="プロキシ")
    @app_commands.describe(
        service="プロキシを変更したいサービス",
        proxy="アクセスするために使用するプロキシのアドレス。",
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
        self,
        interaction: discord.Interaction,
        service: str,
        proxy: str = os.getenv("default_proxy"),
    ):
        if not proxy.startswith("http://") and not proxy.startswith("https://"):
            embed = discord.Embed(
                title="無効なプロキシURLです",
                description="※プロキシは省略可能です。",
                colour=discord.Colour.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

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
    @app_commands.rename(
        service="サービス",
        credential="ログイン情報",
        password="パスワード",
        proxy="プロキシ",
    )
    @app_commands.describe(
        service="リンクしたいサービス",
        credential="Kyashの場合はメールアドレスで、PayPayの場合は電話番号です。",
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
        proxy: str = os.getenv("default_proxy"),
    ):
        if not proxy.startswith("http://") and not proxy.startswith("https://"):
            embed = discord.Embed(
                title="無効なプロキシURLです",
                description="※プロキシは省略可能です。",
                colour=discord.Colour.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if service == "kyash":
            kyash = Kyash()
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
                if (m.channel.type == discord.ChannelType.private) and (
                    m.author.id == interaction.user.id
                ):
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
                return

            try:
                await kyash.validate_otp(message.content)
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "OTPの検証に失敗しました。", ephemeral=True
                )
                await message.reply("OTPの検証に失敗しました。")

            await Database.pool.execute(
                """
                    INSERT INTO kyash (id, email, password, client_uuid, installation_uuid, proxy)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        email = EXCLUDED.email,
                        password = EXCLUDED.password,
                        client_uuid = EXCLUDED.client_uuid,
                        installation_uuid = EXCLUDED.installation_uuid,
                        proxy = EXCLUDED.proxy
                """,
                interaction.user.id,
                self.cipherSuite.encrypt(kyash.email.encode()).decode(),
                self.cipherSuite.encrypt(kyash.password.encode()).decode(),
                kyash.client_uuid,
                kyash.installation_uuid,
                proxy,
            )
            await message.reply(f"アカウントをリンクしました。")

            AccountManager.kyashCache[interaction.user.id] = kyash
        else:
            paypay = PayPay()
            try:
                await paypay.initialize(credential, password)
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "ログインに失敗しました。", ephemeral=True
                )
                return

            await interaction.followup.send(
                "**2分以内**に、SMSに届いた**URLのみ**を**このボットのダイレクトメッセージ**へ送信してください。\nなお、リンクをコピーアンドペーストする際は、リンクを長押しするのではなく、**吹き出しを長押しし、全文コピーした後、リンク以外を削除する**とうまくいきます。",
                ephemeral=True,
            )

            def check(m: discord.Message) -> bool:
                if (m.channel.type == discord.ChannelType.private) and (
                    m.author.id == interaction.user.id
                ):
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
                return

            try:
                await paypay.login(message.content)
            except:
                traceback.print_exc()
                await interaction.followup.send(
                    "OTPの検証に失敗しました。", ephemeral=True
                )
                await message.reply("OTPの検証に失敗しました。")
                return

            await paypay.get_profile()

            await Database.pool.execute(
                """
                    INSERT INTO paypay (id, external_user_id, access_token, refresh_token, device_uuid, client_uuid, phone, password, proxy)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        external_user_id = EXCLUDED.external_user_id,
                        access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token,
                        device_uuid = EXCLUDED.device_uuid,
                        client_uuid = EXCLUDED.client_uuid,
                        phone = EXCLUDED.phone,
                        password = EXCLUDED.password,
                        proxy = EXCLUDED.proxy
                """,
                interaction.user.id,
                paypay.external_user_id,
                self.cipherSuite.encrypt(paypay.access_token.encode()).decode(),
                self.cipherSuite.encrypt(paypay.refresh_token.encode()).decode(),
                paypay.device_uuid,
                paypay.client_uuid,
                self.cipherSuite.encrypt(credential.encode()).decode(),
                self.cipherSuite.encrypt(password.encode()).decode(),
                proxy,
            )
            await message.reply(f"アカウントをリンクしました。")

            AccountManager.paypayCache[interaction.user.id] = paypay
            AccountManager.paypayExternalUserIds[interaction.user.id] = (
                paypay.external_user_id
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AccountLinkCog(bot))
