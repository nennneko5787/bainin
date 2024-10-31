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
        name="link",
        description="KyashやPayPayのアカウントとリンクします。アカウント変更もこっち",
    )
    @app_commands.describe(
        service="リンクしたいサービス",
        credential="Kyashの場合はメールアドレスです。PayPayの場合は電話番号です。",
        password="ログインするために使用するパスワード。",
    )
    @app_commands.choices(
        service=[
            app_commands.Choice(name="Kyash", value="kyash"),
            app_commands.Choice(name="PayPay", value="paypay"),
        ]
    )
    async def linkCommand(
        self,
        interaction: discord.Interaction,
        service: str,
        credential: str,
        password: str,
    ):
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
            paypay = PayPay()
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
