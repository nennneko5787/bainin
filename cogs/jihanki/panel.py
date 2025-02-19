import asyncio
import random
import os
import traceback
import math

import aiohttp
import dotenv
import discord
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands
from snowflake import SnowflakeGenerator

# from .edit import jihankiGroup, goodsGroup

from services.jihanki import JihankiService
from services.database import Database
from services.account import AccountService
from services.payment import PaymentService, MoneyNotEnough

from objects import Jihanki, Good, PaymentType

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


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


class JihankiPanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.botOwner: discord.user = None
        self.ctxUpdateJihanki = app_commands.ContextMenu(
            name="自販機を再読み込み",
            callback=self.updateJihankiContextMenu,
        )
        self.bot.tree.add_command(self.ctxUpdateJihanki)

    async def cog_load(self) -> None:
        self.botOwner = await self.bot.fetch_user(int(os.getenv("ownerId")))

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.ctxUpdateJihanki.name, type=self.ctxUpdateJihanki.type
        )

    async def sendSaleMessage(
        self,
        interaction: discord.Interaction,
        jihanki: Jihanki,
        good: Good,
        service: PaymentType,
    ):
        owner = await self.bot.fetch_user(jihanki.ownerId)

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
                    value=f"{good.name} ({good.price}円)",
                )
                .add_field(
                    name="種別",
                    value=serviceString(service),
                )
            )
            await owner.send(embed=embed)
        except:
            traceback.print_exc()

        try:
            if jihanki.achievementChannelId:
                channel = self.bot.get_channel(jihanki.achievementChannelId)
                if channel:
                    if channel.permissions_for(channel.guild.me).send_messages:
                        embed = (
                            discord.Embed(
                                title="販売実績", colour=discord.Colour.gold()
                            )
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
                                value=f"{good.name} ({good.price}円)",
                            )
                            .set_footer(text=jihanki.name)
                        )
                        await channel.send(embed=embed)
                    else:
                        embed = discord.Embed(
                            title="実績チャンネルの権限を確認してください",
                            description=f"このボットに、**{jihanki.name}**にセットされている実績チャンネルへメッセージを送信する権限を与えてください。",
                            colour=discord.Colour.red(),
                        )
                        await owner.send(embed=embed)
        except:
            traceback.print_exc()

    async def sendPurchaseMessage(
        self, interaction: discord.Interaction, jihanki: Jihanki, good: Good
    ):
        try:
            owner = await self.bot.fetch_user(jihanki.ownerId)
            embed = (
                discord.Embed(title="購入明細書")
                .add_field(
                    name="自販機",
                    value=f"{jihanki.name}",
                )
                .add_field(
                    name="自販機のオーナー",
                    value=f"{owner.display_name} (ID: `{owner.name}`) (UID: {jihanki.ownerId})",
                )
                .add_field(
                    name="商品",
                    value=f"{good.name} ({good.price}円)",
                )
                .add_field(
                    name="商品の内容",
                    value=f"```\n{cipherSuite.decrypt(good.value).decode()}\n```",
                )
            )
            await interaction.user.send(embed=embed)
        except:
            traceback.print_exc()

    async def updateJihanki(self, jihanki: Jihanki, message: discord.Message):
        owner = await self.bot.fetch_user(jihanki.ownerId)

        embed = discord.Embed(
            title=jihanki.name,
            description=f"{jihanki.description}\nオーナー: {owner.mention} (`{owner.name}`)\n最終更新: {discord.utils.format_dt(discord.utils.utcnow())}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。",
            colour=discord.Colour.og_blurple(),
        )

        view = discord.ui.View(timeout=None)
        items = [
            discord.SelectOption(
                label=f"{good.name} ({good.price}円)",
                description=good.description,
                value=index,
                emoji=(
                    discord.PartialEmoji.from_str(good.emoji) if good.emoji else None
                ),
            )
            for index, good in enumerate(jihanki.goods[0:19])
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
                custom_id=f"buy,{jihanki.id}",
                options=items,
            ),
        )

        await message.edit(embed=embed, view=view)

    async def buy(self, interaction: discord.Interaction, customFields: list[str]):
        _interaction = interaction
        await interaction.response.defer(ephemeral=True)
        if interaction.data["values"][0] == "-1":
            return
        jihanki = await JihankiService.getJihanki(
            interaction.user, id=int(customFields[1])
        )

        if not jihanki:
            embed = discord.Embed(
                title="エラーが発生しました。",
                description="自販機が存在しません。\n自販機がすでに削除されている可能性があります",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return

        if jihanki.freezed:
            await interaction.delete_original_response()
            embed = discord.Embed(
                title=f"自販機が凍結されています\n```\n{jihanki.freezed}\n```",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if (jihanki.nsfw) and (
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

        if jihanki.ownerId == interaction.user.id:
            embed = discord.Embed(
                title="自分が販売している商品は購入できません",
                description="ちゃんと販売できているので安心してください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            good = jihanki.goods[int(interaction.data["values"][0])]
        except:
            embed = discord.Embed(
                title="エラーが発生しました。",
                description="商品が存在しません。\n**メッセージを長押し、または右クリック**し、「**アプリ**」を選択し、「**自販機を再読み込み**」を選択してみてください。\n購入しようとしていた商品が存在しない場合は、オーナーに連絡してみてください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return

        asyncio.create_task(self.updateJihanki(jihanki, _interaction.message))

        async def postProcessing(type: PaymentType):
            await self.sendSaleMessage(interaction, jihanki, good, type)
            await self.sendPurchaseMessage(interaction, jihanki, good)

            if not good.infinite:
                jihanki.goods.remove(good)
                await JihankiService.editJihanki(jihanki, editGoods=True)

                await self.updateJihanki(jihanki, interaction.message)

            gen = SnowflakeGenerator(15)
            paymentId = next(gen)

            _jihanki = jihanki
            del _jihanki.goods

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                _jihanki.model_dump_json(),
                good.model_dump_json(),
                interaction.user.id,
                _jihanki.ownerId,
                "BUY",
                -good.price,
            )

            paymentId = next(gen)

            await Database.pool.execute(
                "INSERT INTO history (id, jihanki, good, user_id, to_id, type, amount) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                paymentId,
                _jihanki.model_dump_json(),
                good.model_dump_json(),
                _jihanki.ownerId,
                interaction.user.id,
                "GOT_BUY",
                good.price,
            )

            embed = discord.Embed(
                title="購入しました！",
                description="DMにて購入明細書及び商品の内容を送信しました。\n-# [購入明細はウェブサイトでも閲覧することができます](https://bainin.nennneko5787.net/mypage)",
                colour=discord.Colour.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if good.price == 0:
            await postProcessing(PaymentType.NONE)
            return

        seller = await self.bot.fetch_user(jihanki.ownerId)

        view = discord.ui.View(timeout=300)

        handlePayPay = await AccountService.paypayExists(jihanki.ownerId)
        handleKyash = await AccountService.kyashExists(jihanki.ownerId)

        buyerHasPayPay = await AccountService.paypayExists(interaction.user.id)
        buyerHasKyash = await AccountService.kyashExists(interaction.user.id)

        if handleKyash:
            kyashButton = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Kyashで購入",
                emoji=discord.PartialEmoji.from_str("<a:kyash:1301478014600609832>"),
            )

            async def buyWithKyash(interaction: discord.Interaction):
                if buyerHasKyash:
                    await interaction.response.defer(ephemeral=True)
                    try:
                        await PaymentService.payWithKyash(
                            amount=good.price,
                            buyer=interaction.user,
                            seller=self.botOwner,
                        )
                        if await AccountService.getProxy(
                            seller.id, service="kyash"
                        ) == os.getenv("default_proxy"):
                            price = good.price - math.ceil(good.price * 0.03)
                        else:
                            price = good.price

                        await PaymentService.payWithKyash(
                            amount=price,
                            buyer=self.botOwner,
                            seller=seller,
                        )
                    except MoneyNotEnough:
                        embed = discord.Embed(
                            title="お金が足りません！！",
                            description=f"Kyashをチャージしてください",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    except:
                        embed = discord.Embed(
                            title="エラーが発生しました",
                            description=f"[サポートサーバー](https://discord.gg/PN3KWEnYzX)のサポートチャンネルで\n- 以下のエラーログ\n- 発生手順\nを送信してください。\n```\n{traceback.format_exc()}\n```",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    await postProcessing(PaymentType.KYASH)
                else:
                    _self = self
                    _interaction = interaction

                    class KyashModal(discord.ui.Modal, title="Kyashで購入"):
                        url = discord.ui.TextInput(
                            label="Kyashの送金URL",
                            placeholder="https://kyash.me/payments/XXXXXXXXXXX",
                        )

                        async def on_submit(
                            self, interaction: discord.Interaction
                        ) -> None:
                            await interaction.response.defer(ephemeral=True)
                            try:
                                await PaymentService.receiveKyashUrl(
                                    url=self.url.value,
                                    amount=good.price,
                                    seller=_self.botOwner,
                                )
                                if await AccountService.getProxy(
                                    seller.id, service="kyash"
                                ) == os.getenv("default_proxy"):
                                    price = good.price - math.ceil(good.price * 0.03)
                                else:
                                    price = good.price

                                await PaymentService.payWithKyash(
                                    amount=price,
                                    buyer=_self.botOwner,
                                    seller=seller,
                                )
                            except MoneyNotEnough:
                                embed = discord.Embed(
                                    title="お金が足りません！！",
                                    description=f"送金リンクを作り直してください！！**{good.price}円で！！**",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return
                            except:
                                embed = discord.Embed(
                                    title="エラーが発生しました",
                                    description=f"[サポートサーバー](https://discord.gg/PN3KWEnYzX)のサポートチャンネルで\n- 以下のエラーログ\n- 発生手順\nを送信してください。\n```\n{traceback.format_exc()}\n```",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return
                            await postProcessing(PaymentType.KYASH)

                    await interaction.response.send_modal(KyashModal())

            kyashButton.callback = buyWithKyash
            view.add_item(kyashButton)

        if handlePayPay:
            paypayButton = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="PayPayで購入",
                emoji=discord.PartialEmoji.from_str("<a:kyash:1301478014600609832>"),
            )

            async def buyWithPayPay(interaction: discord.Interaction):
                if buyerHasPayPay:
                    await interaction.response.defer(ephemeral=True)
                    try:
                        await PaymentService.payWithPayPay(
                            amount=good.price,
                            buyer=interaction.user,
                            seller=self.botOwner,
                        )
                        if await AccountService.getProxy(
                            seller.id, service="paypay"
                        ) == os.getenv("default_proxy"):
                            price = good.price - math.ceil(good.price * 0.03)
                        else:
                            price = good.price

                        await PaymentService.payWithPayPay(
                            amount=price,
                            buyer=self.botOwner,
                            seller=seller,
                        )
                    except MoneyNotEnough:
                        embed = discord.Embed(
                            title="お金が足りません！！",
                            description=f"PayPayをチャージしてください",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    except:
                        embed = discord.Embed(
                            title="エラーが発生しました",
                            description=f"[サポートサーバー](https://discord.gg/PN3KWEnYzX)のサポートチャンネルで\n- 以下のエラーログ\n- 発生手順\nを送信してください。\n```\n{traceback.format_exc()}\n```",
                            colour=discord.Colour.red(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                    await postProcessing(PaymentType.PAYPAY)
                else:
                    _self = self
                    _interaction = interaction

                    class PayPayModal(discord.ui.Modal, title="Kyashで購入"):
                        url = discord.ui.TextInput(
                            label="PayPayの送金URL",
                            placeholder="https://kyash.me/payments/XXXXXXXXXXX",
                        )
                        passcode = discord.ui.TextInput(
                            label="送金URLのパスコード",
                            placeholder="パスコードを設定していない場合は省略可",
                            required=False,
                            max_length=4,
                        )

                        async def on_submit(
                            self, interaction: discord.Interaction
                        ) -> None:
                            await interaction.response.defer(ephemeral=True)
                            try:
                                await PaymentService.receivePayPayUrl(
                                    url=self.url.value,
                                    amount=good.price,
                                    seller=_self.botOwner,
                                    passcode=self.passcode.value,
                                )
                                if await AccountService.getProxy(
                                    seller.id, service="paypay"
                                ) == os.getenv("default_proxy"):
                                    price = good.price - math.ceil(good.price * 0.03)
                                else:
                                    price = good.price

                                await PaymentService.payWithPayPay(
                                    amount=price,
                                    buyer=_self.botOwner,
                                    seller=seller,
                                )
                            except MoneyNotEnough:
                                embed = discord.Embed(
                                    title="お金が足りません！！",
                                    description=f"送金リンクを作り直してください！！**{good.price}円で！！**",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return
                            except:
                                embed = discord.Embed(
                                    title="エラーが発生しました",
                                    description=f"[サポートサーバー](https://discord.gg/PN3KWEnYzX)のサポートチャンネルで\n- 以下のエラーログ\n- 発生手順\nを送信してください。\n```\n{traceback.format_exc()}\n```",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return
                            await postProcessing(PaymentType.PAYPAY)

                    await interaction.response.send_modal(PayPayModal())

            paypayButton.callback = buyWithPayPay
            view.add_item(paypayButton)

        if len(view.children) <= 0:
            embed = discord.Embed(
                title="自販機のオーナーがPayPay・Kyashの両方のアカウントをリンクしていません",
                description="自販機のオーナーに「アカウントをリンクしてください！」と言ってあげてください。",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if (handlePayPay and buyerHasPayPay) or (handleKyash and buyerHasKyash):
            linkMessage = "\n**なお、リンクで購入した際お釣りは返ってきませんのでご注意ください。**"
        else:
            linkMessage = ""

        embed = discord.Embed(
            title="決済確認",
            description=f"## {good.name}\n値段: **{good.price}円**\n5分以内に決済を完了してください。{linkMessage}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# DMを許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。",
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
        _jihanki = None

        try:
            select: discord.SelectMenu = message.components[0].children[0]
            customFields = select.custom_id.split(",")
            if len(customFields) == 2:
                if customFields[0] == "buy":
                    _jihanki = int(customFields[1])
        except:
            pass

        if not _jihanki:
            embed = discord.Embed(
                title="それは自販機ではありません！",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        jihanki = await JihankiService.getJihanki(interaction.user, id=int(_jihanki))

        await self.updateJihanki(jihanki, message)

        embed = discord.Embed(
            title="自販機を再読込しました",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # @jihankiGroup.command(name="send", description="自販機を送信します。")
    @app_commands.command(name="send", description="自販機を送信します。")
    @app_commands.autocomplete(_jihanki=JihankiService.getJihankiList)
    @app_commands.rename(_jihanki="自販機", channel="チャンネル")
    @app_commands.describe(
        _jihanki="送信したい自販機",
        channel="送信先チャンネル（デフォルトは現在のチャンネル）",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def sendCommand(
        self,
        interaction: discord.Interaction,
        _jihanki: str,
        channel: discord.TextChannel = None,
    ):
        if not channel:
            channel = interaction.channel

        await interaction.response.defer(ephemeral=True)
        try:
            if _jihanki.isdigit():
                jihanki = await JihankiService.getJihanki(
                    interaction.user, id=int(_jihanki)
                )
            else:
                jihanki = await JihankiService.getJihanki(
                    interaction.user, name=_jihanki
                )
        except:
            embed = discord.Embed(
                title="指定された自販機は存在しません！",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return
        if jihanki.freezed:
            embed = discord.Embed(
                title=f"自販機が凍結されています\n```\n{jihanki.freezed}\n```",
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

        if (jihanki.nsfw) and (
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
    # bot.tree.add_command(goodsGroup)
