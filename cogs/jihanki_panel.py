import asyncio
import os
import traceback
import enum

import aiohttp
import discord
import dotenv
import orjson
from discord.ext import commands
from discord import app_commands
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet

from .database import Database

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


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


class JihankiPanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctxUpdateJihanki = app_commands.ContextMenu(
            name="自販機を再読み込み",
            callback=self.updateJihankiContextMenu,
        )
        self.bot.tree.add_command(self.ctxUpdateJihanki)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.ctxUpdateJihanki.name, type=self.ctxUpdateJihanki.type
        )

    async def getJihankiList(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        jihankiList = await Database.pool.fetch("SELECT * FROM jihanki")
        jihankis = []
        for jihanki in jihankiList:
            if jihanki["name"].startswith(current):
                owner_id = jihanki["owner_id"]
                if owner_id == interaction.user.id:
                    jihankis.append(
                        app_commands.Choice(
                            name=f'{jihanki["name"]}',
                            value=str(jihanki["id"]),
                        )
                    )
        return jihankis

    async def updateJihanki(
        self, jihanki: dict, message: discord.Message, *, goods: dict = None
    ):
        embed = discord.Embed(
            title=jihanki["name"],
            description=f'{jihanki["description"]}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
            colour=discord.Colour.og_blurple(),
        )

        if not goods:
            goods = orjson.loads(jihanki["goods"])

        view = discord.ui.View(timeout=None)
        items = [
            discord.SelectOption(
                label=f'{good["name"]} ({good["price"]}円)',
                description=good["description"],
                value=index,
            )
            for index, good in enumerate(goods)
        ]
        items.insert(
            0,
            discord.SelectOption(
                label="選択してください",
                default=True,
                description="商品を選択できない場合は、一度こちらに戻してください。",
                value="-1",
            ),
        )
        view.add_item(
            discord.ui.Select(
                custom_id=f'buy,{jihanki["id"]}',
                options=items,
            ),
        )

        await message.edit(embed=embed, view=view)

    async def sendSaleMessage(
        self,
        interaction: discord.Interaction,
        jihanki: dict,
        good: dict,
        service: ServiceEnum,
    ):
        try:
            embed = (
                discord.Embed(title="商品が購入されました")
                .set_thumbnail(url=interaction.user.display_avatar.url)
                .add_field(
                    name="ユーザー",
                    value=f"{interaction.user.mention} (ID: `{interaction.user.name}`)",
                )
                .add_field(
                    name="商品",
                    value=f'{good["name"]} ({good["price"]}円)',
                )
                .add_field(
                    name="種別",
                    value=serviceString(service),
                )
            )
            await self.bot.get_user(jihanki["owner_id"]).send(embed=embed)
        except:
            pass

        async def sendLog():
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(
                    os.getenv("sale_webhook"), session=session
                )

                owner = await self.bot.fetch_user(jihanki["owner_id"])
                embed = (
                    discord.Embed(
                        title="商品が購入されました", colour=discord.Colour.green()
                    )
                    .set_thumbnail(url=interaction.user.display_avatar.url)
                    .add_field(
                        name="自販機",
                        value=f"{jihanki['name']}",
                    )
                    .add_field(
                        name="自販機のオーナー",
                        value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {jihanki['owner_id']})",
                    )
                    .add_field(
                        name="購入したユーザー",
                        value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                    )
                    .add_field(
                        name="商品",
                        value=f'{good["name"]} ({good["price"]}円)',
                    )
                    .add_field(
                        name="種別",
                        value=serviceString(service),
                    )
                )

                await webhook.send(embed=embed)

        asyncio.create_task(sendLog())

    async def sendPurchaseMessage(
        self, interaction: discord.Interaction, jihanki: dict, good: dict
    ):
        try:
            owner = self.bot.get_user(jihanki["owner_id"])
            embed = (
                discord.Embed(title="購入明細書")
                .add_field(
                    name="自販機",
                    value=f"{jihanki['name']}",
                )
                .add_field(
                    name="自販機のオーナー",
                    value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {jihanki['owner_id']})",
                )
                .add_field(
                    name="商品",
                    value=f'{good["name"]} ({good["price"]}円)',
                )
                .add_field(
                    name="商品の内容",
                    value=f'```\n{cipherSuite.decrypt(good["value"]).decode()}\n```',
                )
            )
            await interaction.user.send(embed=embed)
        except:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            _interaction = interaction
            if interaction.data["component_type"] == 3:
                customId = interaction.data["custom_id"]
                customFields = customId.split(",")
                if customFields[0] == "buy":
                    await interaction.response.defer(ephemeral=True)
                    if interaction.data["values"][0] == "-1":
                        return
                    jihanki = await Database.pool.fetchrow(
                        "SELECT * FROM jihanki WHERE id = $1", int(customFields[1])
                    )
                    goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])
                    good = goods[int(interaction.data["values"][0])]

                    async def sendLog(errorText: str):
                        async with aiohttp.ClientSession() as session:
                            webhook = discord.Webhook.from_url(
                                os.getenv("error_webhook"), session=session
                            )

                            owner = await self.bot.fetch_user(jihanki["owner_id"])
                            embed = (
                                discord.Embed(
                                    title="エラーが発生しました",
                                    colour=discord.Colour.red(),
                                )
                                .set_thumbnail(url=interaction.user.display_avatar.url)
                                .add_field(
                                    name="自販機",
                                    value=f"{jihanki['name']}",
                                )
                                .add_field(
                                    name="自販機のオーナー",
                                    value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {jihanki['owner_id']})",
                                )
                                .add_field(
                                    name="購入したユーザー",
                                    value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                                )
                                .add_field(
                                    name="商品",
                                    value=f'{good["name"]} ({good["price"]}円)',
                                )
                                .add_field(
                                    name="エラー",
                                    value=f"```\n{errorText}```\n",
                                )
                            )

                            await webhook.send(embed=embed)

                    if good["price"] == 0:
                        await self.sendSaleMessage(
                            interaction, jihanki, good, ServiceEnum.NONE
                        )
                        await self.sendPurchaseMessage(interaction, jihanki, good)
                        await _interaction.delete_original_response()

                        goods.remove(good)
                        goodsJson = orjson.dumps(goods).decode()
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1",
                            goodsJson,
                        )

                        await self.updateJihanki(
                            jihanki, _interaction.message, goods=goods
                        )

                        embed = discord.Embed(
                            title="購入しました！",
                            description="DMにて購入明細書及び商品の内容を送信しました",
                            colour=discord.Colour.green(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return

                    view = discord.ui.View(timeout=300)
                    paypayButton = discord.ui.Button(
                        style=discord.ButtonStyle.danger,
                        label="PayPayで購入",
                        emoji=discord.PartialEmoji.from_str(
                            "<a:paypay:1301478001430626348>"
                        ),
                    )

                    async def buyWithPayPay(interaction: discord.Interaction):
                        await interaction.response.defer(ephemeral=True)

                        ownerPaypayAccount = await Database.pool.fetchrow(
                            "SELECT * FROM paypay WHERE id = $1", jihanki["owner_id"]
                        )
                        if not ownerPaypayAccount:
                            embed = discord.Embed(
                                title="自販機のオーナーがPayPayでの決済を有効化していません",
                                description="オーナーの人に「PayPayのアカウントをリンクしてください！」と言ってあげてください。",
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
                                description=f"</link:{commandId}:> コマンドを使用し、アカウントを紐づけしてください。",
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return
                        paypay = PayPay()
                        try:
                            await paypay.initialize(
                                access_token=cipherSuite.decrypt(
                                    paypayAccount["access_token"]
                                ).decode()
                            )
                        except:
                            try:
                                await paypay.token_refresh(
                                    cipherSuite.decrypt(
                                        paypayAccount["refresh_token"]
                                    ).decode()
                                )
                            except Exception as e:
                                traceback.print_exc()
                                asyncio.create_task(sendLog(traceback.format_exc()))
                                embed = discord.Embed(
                                    title="PayPayでのログインに失敗しました。",
                                    description=str(e),
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return

                        await paypay.get_balance()
                        if (paypay.money + paypay.money_light) < good["price"]:
                            embed = discord.Embed(
                                title="残高が足りません",
                                description="PayPayをチャージしてください",
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

                        try:
                            await paypay.send_money(
                                good["price"], ownerPaypayAccount["external_user_id"]
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

                        await self.sendSaleMessage(
                            interaction, jihanki, good, ServiceEnum.PAYPAY
                        )
                        await self.sendPurchaseMessage(interaction, jihanki, good)
                        await _interaction.delete_original_response()

                        goods.remove(good)
                        goodsJson = orjson.dumps(goods).decode()
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1",
                            goodsJson,
                        )

                        await self.updateJihanki(
                            jihanki, _interaction.message, goods=goods
                        )

                        embed = discord.Embed(
                            title="購入しました！",
                            description="DMにて購入明細書及び商品の内容を送信しました",
                            colour=discord.Colour.green(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)

                    paypayButton.callback = buyWithPayPay

                    kyashButton = discord.ui.Button(
                        style=discord.ButtonStyle.primary,
                        label="Kyashで購入",
                        emoji=discord.PartialEmoji.from_str(
                            "<a:kyash:1301478014600609832>"
                        ),
                    )

                    async def buyWithKyash(interaction: discord.Interaction):
                        await interaction.response.defer(ephemeral=True)

                        ownerKyashAccount = await Database.pool.fetchrow(
                            "SELECT * FROM kyash WHERE id = $1", jihanki["owner_id"]
                        )
                        if not ownerKyashAccount:
                            embed = discord.Embed(
                                title="自販機のオーナーがKyashでの決済を有効化していません",
                                description="オーナーの人に「Kyashのアカウントをリンクしてください！」と言ってあげてください。",
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
                                description=f"</link:{commandId}:> コマンドを使用し、アカウントを紐づけしてください。",
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return
                        ownerKyash = Kyash()
                        try:
                            await ownerKyash.login(
                                email=cipherSuite.decrypt(
                                    ownerKyashAccount["email"]
                                ).decode(),
                                password=cipherSuite.decrypt(
                                    ownerKyashAccount["password"]
                                ).decode(),
                                client_uuid=str(ownerKyashAccount["client_uuid"]),
                                installation_uuid=str(
                                    ownerKyashAccount["installation_uuid"]
                                ),
                            )
                        except Exception as e:
                            traceback.print_exc()
                            asyncio.create_task(sendLog(traceback.format_exc()))
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
                                email=cipherSuite.decrypt(
                                    kyashAccount["email"]
                                ).decode(),
                                password=cipherSuite.decrypt(
                                    kyashAccount["password"]
                                ).decode(),
                                client_uuid=str(kyashAccount["client_uuid"]),
                                installation_uuid=str(
                                    kyashAccount["installation_uuid"]
                                ),
                            )
                        except Exception as e:
                            traceback.print_exc()
                            asyncio.create_task(sendLog(traceback.format_exc()))
                            embed = discord.Embed(
                                title="Kyashでのログインに失敗しました。",
                                description=str(e),
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

                        await kyash.get_wallet()
                        if kyash.all_balance < good["price"]:
                            embed = discord.Embed(
                                title="残高が足りません",
                                description="Kyashをチャージしてください",
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

                        try:
                            await kyash.create_link(
                                amount=good["price"],
                                message=f'{good["name"]} を購入するため。',
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
                            await ownerKyash.link_recieve(url=kyash.created_link)
                        except Exception as e:
                            traceback.print_exc()
                            asyncio.create_task(sendLog(traceback.format_exc()))
                            embed = discord.Embed(
                                title="オーナー側の受け取りに失敗しました",
                                description=str(e),
                                colour=discord.Colour.red(),
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

                        await self.sendSaleMessage(
                            interaction, jihanki, good, ServiceEnum.KYASH
                        )
                        await self.sendPurchaseMessage(interaction, jihanki, good)

                        await _interaction.delete_original_response()

                        goods.remove(good)
                        goodsJson = orjson.dumps(goods).decode()
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1",
                            goodsJson,
                        )

                        await self.updateJihanki(
                            jihanki, _interaction.message, goods=goods
                        )

                        embed = discord.Embed(
                            title="購入しました！",
                            description="DMにて購入明細書及び商品の内容を送信しました",
                            colour=discord.Colour.green(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)

                    kyashButton.callback = buyWithKyash

                    view.add_item(paypayButton)
                    view.add_item(kyashButton)

                    embed = discord.Embed(
                        title="決済方法を選択",
                        description=f'## {good["name"]}\n値段: **{good["price"]}円**\nPayPay または Kyashが使用できます。\n5分以内に決済方法を選択してください。\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
                        colour=discord.Colour.green(),
                    )
                    await interaction.followup.send(
                        embed=embed, view=view, ephemeral=True
                    )
        except KeyError:
            pass

    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def updateJihankiContextMenu(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        await interaction.response.defer(ephemeral=True)
        jihanki = None

        try:
            select: discord.SelectMenu = message.components[0].children[0]
            customFields = select.custom_id.split(",")
            if len(customFields) == 2:
                if customFields[0] == "buy":
                    jihanki = int(customFields[1])
        except:
            pass

        if not jihanki:
            embed = discord.Embed(
                title="それは自販機ではありません！",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        jihanki = await Database.pool.fetchrow(
            "SELECT * FROM jihanki WHERE id = $1", int(jihanki)
        )

        await self.updateJihanki(jihanki, message)

        embed = discord.Embed(
            title="自販機を再読込しました",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="send", description="自販機を送信します。")
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def sendCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        channel: discord.TextChannel = None,
    ):
        if not channel:
            channel = interaction.channel

        await interaction.response.defer(ephemeral=True)
        jihanki = await Database.pool.fetchrow(
            "SELECT * FROM jihanki WHERE id = $1", int(jihanki)
        )
        if jihanki["owner_id"] != interaction.user.id:
            embed = discord.Embed(
                title="その自販機はあなたのものではありません",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not channel.permissions_for(interaction.user).send_messages:
            embed = discord.Embed(
                title="エラーが発生しました",
                description="そのチャンネルに送信する権限はありません",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="ロード中...", description="準備が完了するまで、しばらくお待ち下さい"
        )
        message = await channel.send(embed=embed)

        await self.updateJihanki(jihanki, message)

        embed = discord.Embed(
            title="自販機を送信しました",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(JihankiPanelCog(bot))
