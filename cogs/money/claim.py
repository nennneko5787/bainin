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

from objects import PaymentType
from services.database import Database
from services.money import MoneyService
from .send import moneyGroup

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


class ClaimMoneyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cipherSuite = Fernet(os.getenv("fernet_key").encode())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.data["component_type"] == 2:
                customId = interaction.data["custom_id"]
                customFields = customId.split(",")
                if customFields[0] == "claim":
                    await interaction.response.defer(ephemeral=True)

                    service = PaymentType(customFields[1].upper())
                    amount = int(customFields[2])
                    user = await self.bot.fetch_user(int(customFields[3]))

                    if user.id == interaction.user.id:
                        embed = discord.Embed(
                            title="自分自身には送金できません",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return

                    async def sendLog(errorText: str):
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

                    try:
                        await MoneyService.sendMoney(
                            amount=amount, target=interaction.user, to=user
                        )
                    except:
                        await sendLog(service, traceback.format_exc())

                    await interaction.delete_original_response()

                    gen = SnowflakeGenerator(15)
                    paymentId = next(gen)

                    await Database.pool.execute(
                        "INSERT INTO history (id, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5)",
                        paymentId,
                        interaction.user.id,
                        user.id,
                        (
                            "GOT_PAYPAY"
                            if service == PaymentType.PAYPAY
                            else "GOT_KYASH"
                        ),
                        amount,
                    )

                    paymentId = next(gen)

                    await Database.pool.execute(
                        "INSERT INTO history (id, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5)",
                        paymentId,
                        user.id,
                        interaction.user.id,
                        (
                            "SEND_PAYPAY"
                            if service == PaymentType.PAYPAY
                            else "SEND_KYASH"
                        ),
                        -amount,
                    )

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

                    embed = (
                        discord.Embed(
                            title="送金しました！",
                            description="相手の方にDMが送信されていると思うので、トラブルになったらボット制作者の`nennneko5787`まで言ってくれればサポートします",
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

                    embed = discord.Embed(
                        title="請求",
                        description=f"{interaction.user.mention}さんからの**{amount}円**の請求です！",
                        colour=discord.Colour.blurple(),
                    )
                    await interaction.message.edit(embed=embed)
        except KeyError:
            pass

    @moneyGroup.command(name="claim", description="請求パネルを作成します。")
    @app_commands.rename(amount="請求額")
    @app_commands.describe(
        amount="請求する金額",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def claimCommand(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1],
    ):
        view = discord.ui.View(timeout=None)
        paypayButton = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="PayPayで購入",
            custom_id=f"claim,paypay,{amount},{interaction.user.id}",
            emoji=discord.PartialEmoji.from_str("<a:paypay:1301478001430626348>"),
        )

        kyashButton = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Kyashで購入",
            custom_id=f"claim,kyash,{amount},{interaction.user.id}",
            emoji=discord.PartialEmoji.from_str("<a:kyash:1301478014600609832>"),
        )

        view.add_item(paypayButton)
        view.add_item(kyashButton)

        embed = discord.Embed(
            title="請求",
            description=f"{interaction.user.mention}さんからの**{amount}円**の請求です！",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ClaimMoneyCog(bot))
    bot.tree.add_command(moneyGroup)
