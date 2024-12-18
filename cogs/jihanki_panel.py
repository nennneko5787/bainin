import asyncio
import enum
import os
import traceback
import random
from typing import Callable

import aiohttp
import discord
import dotenv
import orjson
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands
from snowflake import SnowflakeGenerator

from .account import AccountManager
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
        owner = await self.bot.fetch_user(jihanki["owner_id"])

        embed = discord.Embed(
            title=jihanki["name"],
            description=f'{jihanki["description"]}\nオーナー: {owner.mention} (`{owner.name}`)\n最終更新: {discord.utils.format_dt(discord.utils.utcnow())}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
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
                emoji=(
                    discord.PartialEmoji.from_str(good.get("emoji", None))
                    if good.get("emoji", None)
                    else None
                ),
            )
            for index, good in enumerate(goods)
        ]
        random.shuffle(items)
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
        owner = await self.bot.fetch_user(jihanki["owner_id"])

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
            await owner.send(embed=embed)
        except:
            traceback.print_exc()

        if jihanki["achievement_channel_id"]:
            channel = self.bot.get_channel(jihanki["achievement_channel_id"])
            if channel:
                if channel.permissions_for(channel.guild.me).send_messages:
                    embed = (
                        discord.Embed(title="販売実績", colour=discord.Colour.gold())
                        .set_author(
                            name=owner.display_name, icon_url=owner.display_avatar
                        )
                        .set_thumbnail(url=interaction.user.display_avatar)
                        .add_field(
                            name="ユーザー",
                            value=f"{interaction.user.mention}",
                        )
                        .add_field(
                            name="商品",
                            value=f'{good["name"]} ({good["price"]}円)',
                        )
                        .set_footer(text=jihanki["name"])
                    )
                    await channel.send(embed=embed)
                else:
                    embed = discord.Embed(
                        title="実績チャンネルの権限を確認してください",
                        description=f"このボットに、**{jihanki['name']}**にセットされている実績チャンネルへメッセージを送信する権限を与えてください。",
                        colour=discord.Colour.red(),
                    )
                    await owner.send(embed=embed)

    async def sendPurchaseMessage(
        self, interaction: discord.Interaction, jihanki: dict, good: dict
    ):
        try:
            owner = await self.bot.fetch_user(jihanki["owner_id"])
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
            traceback.print_exc()

    class KyashModal(discord.ui.Modal, title="Kyashで購入"):
        def __init__(
            self,
            bot: commands.Bot,
            interaction: discord.Interaction,
            ownerKyash: Kyash,
            jihanki: dict,
            goods: list[dict],
            good: dict,
            sendSaleMessage: Callable,
            sendPurchaseMessage: Callable,
            updateJihanki: Callable,
        ):
            super().__init__()

            self.bot = bot
            self.originalInteraction = interaction
            self.ownerKyash = ownerKyash
            self.jihanki = jihanki
            self.goods = goods
            self.good = good
            self.sendSaleMessage = sendSaleMessage
            self.sendPurchaseMessage = sendPurchaseMessage
            self.updateJihanki = updateJihanki

            self.url = discord.ui.TextInput(
                label="Kyashの送金URL",
                placeholder="https://kyash.me/payments/XXXXXXXXXXX",
            )
            self.add_item(self.url)

        async def sendLog(self, errorText: str):
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(
                    os.getenv("error_webhook"), session=session
                )

                owner = await self.bot.fetch_user(self.jihanki["owner_id"])
                embed = (
                    discord.Embed(
                        title="エラーが発生しました",
                        colour=discord.Colour.red(),
                    )
                    .set_thumbnail(url=self.originalInteraction.user.display_avatar.url)
                    .add_field(
                        name="自販機",
                        value=f"{self.jihanki['name']}",
                    )
                    .add_field(
                        name="自販機のオーナー",
                        value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {self.jihanki['owner_id']})",
                    )
                    .add_field(
                        name="購入したユーザー",
                        value=f"{self.originalInteraction.user.mention}\n`{self.originalInteraction.user.name}`",
                    )
                    .add_field(
                        name="商品",
                        value=f'{self.good["name"]} ({self.good["price"]}円)',
                    )
                    .add_field(
                        name="エラー",
                        value=f"```\n{errorText}```\n",
                    )
                )

                await webhook.send(embed=embed)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                await self.ownerKyash.link_check(self.url.value)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="リンクのチェックに失敗しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if int(self.ownerKyash.link_amount) < self.good["price"]:
                embed = discord.Embed(
                    title="お金が足りません！！",
                    description=f"送金リンクを作り直してください！！**{self.good['price']}円で！！**",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                await self.ownerKyash.link_recieve(
                    self.url.value, self.ownerKyash.link_uuid
                )
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="オーナー側の受け取りに失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                if int(self.ownerKyash.link_amount) > self.good["price"]:
                    amount = int(self.ownerKyash.link_amount) - self.good["price"]
                    await self.ownerKyash.create_link(amount)
                    embed = discord.Embed(
                        title="多く払った分をお返しします",
                        description=self.ownerKyash.created_link,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    await interaction.user.send(embed=embed)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="多く払った分を返金する処理に失敗しました",
                    description=f"あとで返金してもらってください\n```\n{str(e)}\n```",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            await self.sendSaleMessage(
                interaction, self.jihanki, self.good, ServiceEnum.KYASH
            )
            await self.sendPurchaseMessage(interaction, self.jihanki, self.good)

            if not self.good.get("infinite", False):
                self.goods.remove(self.good)
                goodsJson = orjson.dumps(self.goods).decode()
                await Database.pool.execute(
                    "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                    goodsJson,
                    self.jihanki["id"],
                )

                await self.updateJihanki(
                    self.jihanki, self.originalInteraction.message, goods=self.goods
                )

            await interaction.delete_original_response()

            gen = SnowflakeGenerator(15)
            paymentId = next(gen)

            _jihanki = dict(self.jihanki)
            del _jihanki["goods"]

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                orjson.dumps(_jihanki).decode(),
                orjson.dumps(self.good).decode(),
                interaction.user.id,
                _jihanki["owner_id"],
                "BUY_KYASH",
                -self.good["price"],
            )

            paymentId = next(gen)

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                _jihanki,
                self.good,
                _jihanki["owner_id"],
                interaction.user.id,
                "GOT_BUY_KYASH",
                self.good["price"],
            )

            embed = discord.Embed(
                title="購入しました！",
                description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                colour=discord.Colour.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    class PayPayModal(discord.ui.Modal, title="PayPayで購入"):
        def __init__(
            self,
            bot: commands.Bot,
            interaction: discord.Interaction,
            ownerPayPay: PayPay,
            jihanki: dict,
            goods: list[dict],
            good: dict,
            sendSaleMessage: Callable,
            sendPurchaseMessage: Callable,
            updateJihanki: Callable,
        ):
            super().__init__()

            self.bot = bot
            self.originalInteraction = interaction
            self.ownerPayPay = ownerPayPay
            self.jihanki = jihanki
            self.goods = goods
            self.good = good
            self.sendSaleMessage = sendSaleMessage
            self.sendPurchaseMessage = sendPurchaseMessage
            self.updateJihanki = updateJihanki

            self.url = discord.ui.TextInput(
                label="PayPayの送金URL",
                placeholder="https://pay.paypay.ne.jp/XXXXXXXXXXX",
            )
            self.add_item(self.url)

            self.password = discord.ui.TextInput(
                label="送金URLのパスワード(必要な場合)",
                placeholder="0000",
            )
            self.add_item(self.password)

        async def sendLog(self, errorText: str):
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(
                    os.getenv("error_webhook"), session=session
                )

                owner = await self.bot.fetch_user(self.jihanki["owner_id"])
                embed = (
                    discord.Embed(
                        title="エラーが発生しました",
                        colour=discord.Colour.red(),
                    )
                    .set_thumbnail(url=self.originalInteraction.user.display_avatar.url)
                    .add_field(
                        name="自販機",
                        value=f"{self.jihanki['name']}",
                    )
                    .add_field(
                        name="自販機のオーナー",
                        value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {self.jihanki['owner_id']})",
                    )
                    .add_field(
                        name="購入したユーザー",
                        value=f"{self.originalInteraction.user.mention}\n`{self.originalInteraction.user.name}`",
                    )
                    .add_field(
                        name="商品",
                        value=f'{self.good["name"]} ({self.good["price"]}円)',
                    )
                    .add_field(
                        name="エラー",
                        value=f"```\n{errorText}```\n",
                    )
                )

                await webhook.send(embed=embed)

        async def on_submit(self, interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)

            try:
                await self.ownerPayPay.link_check(self.url.value)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="リンクのチェックに失敗しました。",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if int(self.ownerPayPay.link_amount) < self.good["price"]:
                embed = discord.Embed(
                    title="お金が足りません！！",
                    description=f"送金リンクを作り直してください！！**{self.good['price']}円で！！**",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            linkAmount: int = int(self.ownerPayPay.link_amount)

            try:
                await self.ownerPayPay.link_receive(self.url.value, self.password.value)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="オーナー側の受け取りに失敗しました",
                    description=str(e),
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                if linkAmount > self.good["price"]:
                    amount: int = linkAmount - self.good["price"]
                    await self.ownerPayPay.create_link(amount)
                    embed = discord.Embed(
                        title="多く払った分をお返しします",
                        description=self.ownerPayPay.created_link,
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    await interaction.user.send(embed=embed)
            except Exception as e:
                traceback.print_exc()
                asyncio.create_task(self.sendLog(traceback.format_exc()))
                embed = discord.Embed(
                    title="多く払った分を返金する処理に失敗しました",
                    description=f"あとで返金してもらってください\n```\n{str(e)}\n```",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            await self.sendSaleMessage(
                interaction, self.jihanki, self.good, ServiceEnum.KYASH
            )
            await self.sendPurchaseMessage(interaction, self.jihanki, self.good)

            if not self.good.get("infinite", False):
                self.goods.remove(self.good)
                goodsJson = orjson.dumps(self.goods).decode()
                await Database.pool.execute(
                    "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                    goodsJson,
                    self.jihanki["id"],
                )

                await self.updateJihanki(
                    self.jihanki, self.originalInteraction.message, goods=self.goods
                )

            await interaction.delete_original_response()

            gen = SnowflakeGenerator(15)
            paymentId = next(gen)

            _jihanki = dict(self.jihanki)
            del _jihanki["goods"]

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                orjson.dumps(_jihanki).decode(),
                orjson.dumps(self.good).decode(),
                interaction.user.id,
                _jihanki["owner_id"],
                "BUY_PAYPAY",
                -self.good["price"],
            )

            paymentId = next(gen)

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                orjson.dumps(_jihanki).decode(),
                orjson.dumps(self.good).decode(),
                _jihanki["owner_id"],
                interaction.user.id,
                "GOT_BUY_PAYPAY",
                self.good["price"],
            )

            embed = discord.Embed(
                title="購入しました！",
                description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                colour=discord.Colour.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def buy(self, interaction: discord.Interaction, customFields: list[str]):
        _interaction = interaction
        await interaction.response.defer(ephemeral=True)
        if interaction.data["values"][0] == "-1":
            return
        jihanki = await Database.pool.fetchrow(
            "SELECT * FROM jihanki WHERE id = $1", int(customFields[1])
        )

        if not jihanki:
            embed = discord.Embed(
                title="エラーが発生しました。",
                description="自販機が存在しません。\n自販機がすでに削除されている可能性があります",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return

        if jihanki["freezed"]:
            await interaction.delete_original_response()
            embed = discord.Embed(
                title=f'自販機が凍結されています\n```\n{jihanki["freezed"]}\n```',
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if (jihanki["nsfw"]) and (
            (not interaction.channel.is_nsfw())
            and (
                (interaction.channel.guild.nsfw_level != 1)
                and (interaction.channel.guild.nsfw_level != 3)
            )
        ):
            await interaction.delete_original_response()
            embed = discord.Embed(
                title="エラーが発生しました",
                description="全年齢対象のチャンネルで18歳以上対象の自販機の商品を購入することはできません。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if jihanki["owner_id"] == interaction.user.id:
            embed = discord.Embed(
                title="自分が販売している商品は購入できません",
                description="ちゃんと販売できているので安心してください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])
        try:
            good = goods[int(interaction.data["values"][0])]
        except:
            embed = discord.Embed(
                title="エラーが発生しました。",
                description="商品が存在しません。\n**メッセージを長押し、または右クリック**し、「**アプリ**」を選択し、「**自販機を再読み込み**」を選択してみてください。\n購入しようとしていた商品が存在しない場合は、オーナーに連絡してみてください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return

        asyncio.create_task(
            self.updateJihanki(jihanki, _interaction.message, goods=goods)
        )

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
            await self.sendSaleMessage(interaction, jihanki, good, ServiceEnum.NONE)
            await self.sendPurchaseMessage(interaction, jihanki, good)

            if not good.get("infinite", False):
                goods.remove(good)
                goodsJson = orjson.dumps(goods).decode()
                await Database.pool.execute(
                    "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                    goodsJson,
                    jihanki["id"],
                )

                await self.updateJihanki(jihanki, interaction.message, goods=goods)

            gen = SnowflakeGenerator(15)
            paymentId = next(gen)

            _jihanki = dict(jihanki)
            del _jihanki["goods"]

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                orjson.dumps(_jihanki).decode(),
                orjson.dumps(good).decode(),
                interaction.user.id,
                _jihanki["owner_id"],
                "BUY",
                -good["price"],
            )

            paymentId = next(gen)

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                orjson.dumps(_jihanki).decode(),
                orjson.dumps(good).decode(),
                _jihanki["owner_id"],
                interaction.user.id,
                "GOT_BUY",
                good["price"],
            )

            embed = discord.Embed(
                title="購入しました！",
                description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                colour=discord.Colour.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        view = discord.ui.View(timeout=300)

        try:
            ownerPayPay: PayPay = await AccountManager.loginPayPay(jihanki["owner_id"])
        except:
            traceback.print_exc()
            ownerPayPay = None

        try:
            paypay: PayPay = await AccountManager.loginPayPay(interaction.user.id)
        except:
            traceback.print_exc()
            paypay = None

        try:
            ownerKyash: Kyash = await AccountManager.loginKyash(jihanki["owner_id"])
        except:
            traceback.print_exc()
            ownerKyash = None

        try:
            kyash: Kyash = await AccountManager.loginKyash(interaction.user.id)
        except:
            traceback.print_exc()
            kyash = None

        isPayPay = False
        isKyash = False

        if ownerKyash:
            kyashButton = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Kyashで購入",
                emoji=discord.PartialEmoji.from_str("<a:kyash:1301478014600609832>"),
            )
            if kyash:

                async def buyWithKyash(interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=True)

                    try:
                        await kyash.get_wallet()
                    except Exception as e:
                        traceback.print_exc()
                        asyncio.create_task(sendLog(traceback.format_exc()))
                        embed = discord.Embed(
                            title="Kyashのアカウント情報の取得に失敗しました。",
                            description=str(e),
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    if int(kyash.all_balance) < good["price"]:
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

                    await self.sendSaleMessage(
                        interaction, jihanki, good, ServiceEnum.KYASH
                    )
                    await self.sendPurchaseMessage(interaction, jihanki, good)

                    if not good.get("infinite", False):
                        goods.remove(good)
                        goodsJson = orjson.dumps(goods).decode()
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                            goodsJson,
                            jihanki["id"],
                        )

                        await self.updateJihanki(
                            jihanki, _interaction.message, goods=goods
                        )

                    await interaction.delete_original_response()

                    gen = SnowflakeGenerator(15)
                    paymentId = next(gen)

                    _jihanki = dict(jihanki)
                    del _jihanki["goods"]

                    await Database.pool.execute(
                        "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        paymentId,
                        orjson.dumps(_jihanki).decode(),
                        orjson.dumps(good).decode(),
                        interaction.user.id,
                        _jihanki["owner_id"],
                        "BUY_KYASH",
                        -good["price"],
                    )

                    paymentId = next(gen)

                    await Database.pool.execute(
                        "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        paymentId,
                        orjson.dumps(_jihanki).decode(),
                        orjson.dumps(good).decode(),
                        _jihanki["owner_id"],
                        interaction.user.id,
                        "GOT_BUY_KYASH",
                        good["price"],
                    )

                    embed = discord.Embed(
                        title="購入しました！",
                        description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                        colour=discord.Colour.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

            else:

                async def buyWithKyash(interaction: discord.Interaction):
                    modal = self.KyashModal(
                        self.bot,
                        _interaction,
                        ownerKyash,
                        jihanki,
                        goods,
                        good,
                        self.sendSaleMessage,
                        self.sendPurchaseMessage,
                        self.updateJihanki,
                    )
                    await interaction.response.send_modal(modal)

            kyashButton.callback = buyWithKyash
            view.add_item(kyashButton)
            isKyash = True

        if ownerPayPay:
            paypayButton = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="PayPayで購入",
                emoji=discord.PartialEmoji.from_str("<paypay:1301478001430626348>"),
            )

            if paypay:

                async def buyWithPayPay(interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=True)

                    try:
                        await paypay.get_balance()
                    except Exception as e:
                        traceback.print_exc()
                        asyncio.create_task(sendLog(traceback.format_exc()))
                        embed = discord.Embed(
                            title="PayPayのアカウント情報の取得に失敗しました。",
                            description=str(e),
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return

                    if ((int(paypay.money or 0)) + (int(paypay.money_light or 0))) < good[
                        "price"
                    ]:
                        embed = discord.Embed(
                            title="残高が足りません",
                            description="PayPayをチャージしてください",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return

                    try:
                        await paypay.send_money(
                            good["price"],
                            AccountManager.paypayExternalUserIds[jihanki["owner_id"]],
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

                    if not good.get("infinite", False):
                        goods.remove(good)
                        goodsJson = orjson.dumps(goods).decode()
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                            goodsJson,
                            jihanki["id"],
                        )

                        await self.updateJihanki(
                            jihanki, _interaction.message, goods=goods
                        )

                    await interaction.delete_original_response()

                    gen = SnowflakeGenerator(15)
                    paymentId = next(gen)

                    _jihanki = dict(jihanki)
                    del _jihanki["goods"]

                    await Database.pool.execute(
                        "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        paymentId,
                        orjson.dumps(_jihanki).decode(),
                        orjson.dumps(good).decode(),
                        interaction.user.id,
                        _jihanki["owner_id"],
                        "BUY_PAYPAY",
                        -good["price"],
                    )

                    paymentId = next(gen)

                    await Database.pool.execute(
                        "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        paymentId,
                        orjson.dumps(_jihanki).decode(),
                        orjson.dumps(good).decode(),
                        _jihanki["owner_id"],
                        interaction.user.id,
                        "GOT_BUY_PAYPAY",
                        good["price"],
                    )

                    embed = discord.Embed(
                        title="購入しました！",
                        description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                        colour=discord.Colour.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)

            else:

                async def buyWithPayPay(interaction: discord.Interaction):
                    modal = self.PayPayModal(
                        self.bot,
                        _interaction,
                        ownerPayPay,
                        jihanki,
                        goods,
                        good,
                        self.sendSaleMessage,
                        self.sendPurchaseMessage,
                        self.updateJihanki,
                    )
                    await interaction.response.send_modal(modal)

            paypayButton.callback = buyWithPayPay
            view.add_item(paypayButton)
            isPayPay = True

        if (not isKyash) and (not isPayPay):
            embed = discord.Embed(
                title="自販機のオーナーがPayPay・Kyashの両方のアカウントをリンクしていません",
                description="自販機のオーナーに「アカウントをリンクしてください！」と言ってあげてください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="決済確認",
            description=f'## {good["name"]}\n値段: **{good["price"]}円**\n5分以内に決済を完了してください。\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
            colour=discord.Colour.blurple(),
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if interaction.data["component_type"] == 3:
                customId = interaction.data["custom_id"]
                customFields = customId.split(",")
                if customFields[0] == "buy":
                    await self.buy(interaction, customFields)
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
    @app_commands.rename(jihanki="自販機", channel="チャンネル")
    @app_commands.describe(
        jihanki="送信したい自販機",
        channel="送信先チャンネル（デフォルトは現在のチャンネル）",
    )
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
        try:
            jihanki = await Database.pool.fetchrow(
                "SELECT * FROM jihanki WHERE id = $1", int(jihanki)
            )
        except:
            jihanki = await Database.pool.fetchrow(
                "SELECT * FROM jihanki WHERE name LIKE $1 AND owner_id = $2 LIMIT 1",
                jihanki,
                interaction.user.id,
            )
            
        if not jihanki:
            embed = discord.Embed(title="自販機が存在しません。", description="名前が間違っていないかご確認ください。", colour=discord.Colour.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

            
        if jihanki["owner_id"] != interaction.user.id:
            embed = discord.Embed(
                title="その自販機はあなたのものではありません",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if jihanki["freezed"]:
            embed = discord.Embed(
                title=f'自販機が凍結されています\n```\n{jihanki["freezed"]}\n```',
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not channel.permissions_for(interaction.guild.me).send_messages:
            embed = discord.Embed(
                title="エラーが発生しました",
                description=f"このボットがそのチャンネルに送信する権限がありません。\n{interaction.guild.me.mention} に`メッセージを送信`する権限を与えてください。",
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

        if (jihanki["nsfw"]) and (
            (not channel.is_nsfw())
            and ((channel.guild.nsfw_level != 1) and (channel.guild.nsfw_level != 3))
        ):
            embed = discord.Embed(
                title="エラーが発生しました",
                description="18歳以上対象の自販機を全年齢対象のチャンネルに配置することはできません。",
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
