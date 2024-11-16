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

from .account import AccountManager, AccountNotLinkedException, FailedToLoginException
from .database import Database

dotenv.load_dotenv()


class ServiceEnum(enum.Enum):
    NONE = "NONE"
    PAYPAY = "PAYPAY"
    KYASH = "KYASH"

    @classmethod
    def valueOf(cls, targetValue):
        for e in ServiceEnum:
            if e.value == targetValue:
                return e
        return ServiceEnum.NONE


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

                    service = ServiceEnum.valueOf(customFields[1].upper())
                    amount = int(customFields[2])
                    user = await self.bot.fetch_user(int(customFields[3]))

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

                    if service == ServiceEnum.KYASH:
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
                            kyash: Kyash = await AccountManager.loginKyash(
                                interaction.user.id
                            )
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
                            asyncio.create_task(sendLog(traceback.format_exc()))
                            embed = discord.Embed(
                                title="送金に失敗しました",
                                description=str(e),
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

                        try:
                            await ownerKyash.link_check(kyash.created_link)

                            await ownerKyash.link_recieve(
                                kyash.created_link, ownerKyash.link_uuid
                            )
                        except Exception as e:
                            traceback.print_exc()
                            await kyash.link_cancel(
                                kyash.created_link, ownerKyash.link_uuid
                            )
                            asyncio.create_task(sendLog(traceback.format_exc()))
                            embed = discord.Embed(
                                title="オーナー側の受け取りに失敗しました",
                                description=str(e),
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return
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
                            paypay: PayPay = await AccountManager.loginPayPay(
                                interaction.user.id
                            )
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

                        if ((paypay.money or 0) + (paypay.money_light or 0)) < amount:
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
                            asyncio.create_task(sendLog(traceback.format_exc()))
                            embed = discord.Embed(
                                title="送金に失敗しました",
                                description=str(e),
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

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

    @app_commands.command(name="claim", description="請求パネルを作成します。")
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
