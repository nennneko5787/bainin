import os

import discord
import dotenv
import emoji
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands
from snowflake import SnowflakeGenerator

from objects import Good, Jihanki
from services.jihanki import JihankiService

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


def isEmoji(s: str) -> bool:
    return s in emoji.EMOJI_DATA


class AddGoodsModal(discord.ui.Modal, title="商品を追加"):
    def __init__(
        self,
        jihanki: str,
        name: str,
        description: str,
        price: int,
        infinite: bool = False,
        emoji: str = None,
        title="商品を追加",
    ):
        super().__init__(title=title)
        self._jihanki = jihanki
        self.name = name
        self.description = description
        self.price = price
        self.infinite = infinite
        self.emoji = emoji
        if len(name) >= 20:
            self.goodsValue = discord.ui.TextInput(
                label=f'"{name[0:20]}"... の中身',
                style=discord.TextStyle.long,
                placeholder="内容をここに入力",
            )
            self.add_item(self.goodsValue)
        else:
            self.goodsValue = discord.ui.TextInput(
                label=f'"{name}"の中身',
                style=discord.TextStyle.long,
                placeholder="内容をここに入力",
            )
            self.add_item(self.goodsValue)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            if self._jihanki.isdigit():
                jihanki = await JihankiService.getJihanki(
                    interaction.user, id=int(self._jihanki)
                )
            else:
                jihanki = await JihankiService.getJihanki(
                    interaction.user, name=self._jihanki
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

        if self.emoji:
            emoji = discord.PartialEmoji.from_str(self.emoji)
            if not emoji.is_custom_emoji() and not isEmoji(emoji.name):
                embed = discord.Embed(
                    title="絵文字が無効です！\n❤️などの通常の絵文字は`:heart:`ではなく`❤️`の状態で入力する必要があります。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        jihanki.goods.append(
            Good(
                name=self.name,
                description=self.description,
                price=self.price,
                infinite=self.infinite,
                value=cipherSuite.encrypt(self.goodsValue.value.encode()).decode(),
                emoji=self.emoji,
            )
        )

        await JihankiService.editJihanki(jihanki, editGoods=True)
        embed = discord.Embed(
            title="自販機に商品を追加しました", colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class EditGoodModal(discord.ui.Modal):
    def __init__(
        self,
        jihanki: Jihanki,
        select: int,
        interaction: discord.Interaction,
    ):
        super().__init__(title=f"{jihanki.goods[select].name} を編集")

        self.jihanki: Jihanki = jihanki
        self.select: int = select
        self.interaction: discord.Interaction = interaction

        self.name = discord.ui.TextInput(
            label="商品の名前",
            placeholder="愛情",
            default=jihanki.goods[self.select].name,
        )
        self.add_item(self.name)

        self.description = discord.ui.TextInput(
            label="商品の説明",
            placeholder="私の愛情を受け取ることができます",
            default=jihanki.goods[self.select].description,
        )
        self.add_item(self.description)

        self.price = discord.ui.TextInput(
            label="価格",
            placeholder="数字以外は受け付けません",
            default=jihanki.goods[self.select].price,
        )
        self.add_item(self.price)

        self.emoji = discord.ui.TextInput(
            label="ラベルの絵文字",
            placeholder="絵文字以外は受け付けません",
            default=jihanki.goods[self.select].emoji,
            required=False,
        )
        self.add_item(self.emoji)

        self.value = discord.ui.TextInput(
            label="内容",
            placeholder="Chu!😘",
            style=discord.TextStyle.long,
            default=cipherSuite.decrypt(jihanki.goods[self.select].value).decode(),
        )
        self.add_item(self.value)

    def convertToInteger(self, numeric: str) -> str | bool:
        try:
            return int(numeric)
        except ValueError:
            return False

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        self.jihanki.goods[self.select].name = self.name.value
        self.jihanki.goods[self.select].description = self.description.value
        price = self.convertToInteger(self.price.value)

        if (price is False) or (price < 0):
            embed = discord.Embed(
                title="エラーが発生しました",
                description="価格は0以上の整数でなければなりません",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)
            return

        self.jihanki.goods[self.select].price = price
        self.jihanki.goods[self.select].value = cipherSuite.encrypt(
            self.value.value.encode()
        ).decode()
        if self.emoji.value:
            emoji = discord.PartialEmoji.from_str(self.emoji.value)
            if not emoji.is_custom_emoji() and not isEmoji(emoji.name):
                embed = discord.Embed(
                    title="絵文字が無効です！\n❤️などの通常の絵文字は`:heart:`ではなく`❤️`の状態で入力する必要があります。",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            self.jihanki.goods[self.select].emoji = self.emoji.value
        else:
            self.jihanki.goods[self.select].emoji = None

        await JihankiService.editJihanki(self.jihanki, editGoods=True)

        embed = discord.Embed(
            title="編集しました！",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f'{good.name} ({good.price}円) {"(在庫無限)" if good.infinite else ""}',
                    description=good.description,
                    value=index,
                )
                for index, good in enumerate(self.jihanki.goods[0:20])
            ]
        )

        async def editGoodsOnSelect(_interaction: discord.Interaction):
            await _interaction.response.send_modal(
                EditGoodModal(
                    self.jihanki,
                    int(_interaction.data["values"][0]),
                    interaction,
                )
            )

        select.callback = editGoodsOnSelect
        view.add_item(select)
        embed = discord.Embed(
            title="確認・編集する商品を選択してください", colour=discord.Colour.pink()
        )

        await self.interaction.edit_original_response(embed=embed, view=view)


context = app_commands.AppCommandContext(guild=True)
installs = app_commands.AppInstallationType(guild=True)
jihankiGroup = app_commands.Group(
    name="jihanki",
    description="自販機関連のコマンド。",
    allowed_contexts=context,
    allowed_installs=installs,
)
goodsGroup = app_commands.Group(
    name="goods", description="商品関連のコマンド。", parent=jihankiGroup
)


class JihankiEditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # @jihankiGroup.command(name="make", description="自販機を作成します。")
    @app_commands.command(name="make", description="自販機を作成します。")
    @app_commands.rename(
        name="名前",
        description="説明",
        achievement="実績チャンネル",
        nsfw="18歳以上対象かどうか",
        shuffle="商品の並びをシャッフル",
    )
    @app_commands.describe(
        name="自販機の名前",
        description="自販機の説明",
        achievement="実績を送信するチャンネル",
        nsfw="自販機が18歳以上対象の商品を販売するかどうか",
        shuffle="商品を購入されるたびに商品の並びをシャッフルするかどうか",
    )
    @app_commands.choices(
        nsfw=[
            app_commands.Choice(name="はい", value=True),
            app_commands.Choice(name="いいえ", value=False),
        ],
        shuffle=[
            app_commands.Choice(name="はい", value=True),
            app_commands.Choice(name="いいえ", value=False),
        ],
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def makeCommand(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        nsfw: app_commands.Choice[int],
        achievement: discord.TextChannel = None,
        shuffle: app_commands.Choice[int] = None,
    ):
        if shuffle is None:
            shuffle = app_commands.Choice(name="いいえ", value=False)

        if achievement:
            if not achievement.permissions_for(interaction.guild.me).send_messages:
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="実績チャンネルにこのボットがメッセージを送信する権限がありません。",
                    colour=discord.Colour.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            achievementChannelId = achievement.id
        else:
            achievementChannelId = None

        await interaction.response.defer(ephemeral=True)
        gen = SnowflakeGenerator(39)
        id = next(gen)
        jihanki = Jihanki(
            id=id,
            name=name,
            description=description,
            goods=[],
            owner_id=interaction.user.id,
            achievement_channel_id=achievementChannelId,
            nsfw=nsfw.value,
            freezed=None,
            shuffle=shuffle.value,
        )
        await JihankiService.makeJihanki(jihanki)

        embed = discord.Embed(
            title="⚠️注意",
            description="児童ポルノや、日本の法律に違反している商品の販売は禁止です。\n販売していたことが判明していた場合、運営は自販機の販売停止を行います。\n詳しくは利用規約をお読みください。\nhttps://bainin.nennneko5787.net/terms",
            colour=discord.Colour.yellow(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="⚠️注意",
            description=f"自販機を作るだけでは、実際に売上を上げることはできません！\n売上を上げたい場合、`/account link` コマンドを実行してPayPayかKyashのアカウントをリンクする必要があります。\nわからないときはいつでも[サポートサーバー](https://discord.gg/PN3KWEnYzX)へどうぞ。",
            colour=discord.Colour.yellow(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="自販機を作成しました",
            description="`/addgoods` コマンドで商品を追加できます",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # @jihankiGroup.command(name="delete", description="自販機を削除します。")
    @app_commands.command(name="delete", description="自販機を削除します。")
    @app_commands.autocomplete(_jihanki=JihankiService.getJihankiList)
    @app_commands.rename(_jihanki="自販機")
    @app_commands.describe(
        _jihanki="削除したい自販機",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def deleteCommand(
        self,
        interaction: discord.Interaction,
        _jihanki: str,
    ):
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
        await JihankiService.deleteJihanki(jihanki)

    # @jihankiGroup.command(name="edit", description="自販機を編集します。")
    @app_commands.command(name="edit", description="自販機を編集します。")
    @app_commands.autocomplete(_jihanki=JihankiService.getJihankiList)
    @app_commands.rename(
        _jihanki="自販機",
        name="名前",
        description="説明",
        achievement="実績チャンネル",
        nsfw="18歳以上対象かどうか",
        shuffle="商品の並びをシャッフル",
    )
    @app_commands.describe(
        _jihanki="編集したい自販機",
        name="自販機の名前",
        description="自販機の説明",
        achievement="実績チャンネル",
        nsfw="自販機が18歳以上対象の商品を販売するかどうか。",
        shuffle="商品を購入されるたびに商品の並びをシャッフルするかどうか",
    )
    @app_commands.choices(
        nsfw=[
            app_commands.Choice(name="はい", value=True),
            app_commands.Choice(name="いいえ", value=False),
        ],
        shuffle=[
            app_commands.Choice(name="はい", value=True),
            app_commands.Choice(name="いいえ", value=False),
        ],
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def editCommand(
        self,
        interaction: discord.Interaction,
        _jihanki: str,
        name: str,
        description: str,
        nsfw: app_commands.Choice[int],
        achievement: discord.TextChannel = None,
        shuffle: app_commands.Choice[int] = None,
    ):
        if shuffle is None:
            shuffle = app_commands.Choice(name="いいえ", value=False)

        if achievement:
            if not achievement.permissions_for(interaction.guild.me).send_messages:
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="実績チャンネルにこのボットがメッセージを送信する権限がありません。",
                    colour=discord.Colour.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            achievementChannelId = achievement.id
        else:
            achievementChannelId = None
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
        jihanki.name = name
        jihanki.description = description
        jihanki.nsfw = nsfw.value
        jihanki.achievementChannelId = achievementChannelId
        jihanki.shuffle = shuffle.value
        await JihankiService.editJihanki(jihanki)

    # @goodsGroup.command(name="add", description="自販機に商品を追加します。")
    @app_commands.command(name="addgoods", description="自販機に商品を追加します。")
    @app_commands.autocomplete(jihanki=JihankiService.getJihankiList)
    @app_commands.rename(
        jihanki="自販機",
        name="名前",
        description="説明",
        price="価格",
        infinite="在庫無限",
        emoji="ラベルの絵文字",
    )
    @app_commands.describe(
        jihanki="商品を追加したい自販機",
        name="商品の名前",
        description="商品の説明",
        price="商品の価格",
        infinite="商品の在庫が無限かどうか（デフォルトはいいえ）",
        emoji="商品のラベルにつける絵文字",
    )
    @app_commands.choices(
        infinite=[
            app_commands.Choice(name="はい", value=True),
            app_commands.Choice(name="いいえ", value=False),
        ]
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def addGoodsCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        name: app_commands.Range[str, 1, 100],
        description: app_commands.Range[str, 1, 100],
        price: app_commands.Range[int, 0],
        infinite: app_commands.Choice[int] = None,
        emoji: str = None,
    ):
        await interaction.response.send_modal(
            AddGoodsModal(
                jihanki,
                name,
                description,
                price,
                infinite.value if infinite else False,
                emoji,
            )
        )

    # @goodsGroup.command(name="edit", description="自販機の商品を編集・確認します。")
    @app_commands.command(
        name="editgoods", description="自販機の商品を編集・確認します。"
    )
    @app_commands.autocomplete(_jihanki=JihankiService.getJihankiList)
    @app_commands.rename(_jihanki="自販機")
    @app_commands.describe(_jihanki="商品を編集したい自販機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def editGoodsCommand(
        self,
        interaction: discord.Interaction,
        _jihanki: str,
    ):
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
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f'{good.name} ({good.price}円) {"(在庫無限)" if good.infinite else ""}',
                    description=good.description,
                    value=index,
                )
                for index, good in enumerate(jihanki.goods[0:20])
            ]
        )

        async def editGoodsOnSelect(_interaction: discord.Interaction):
            await _interaction.response.send_modal(
                EditGoodModal(
                    jihanki,
                    int(_interaction.data["values"][0]),
                    interaction,
                )
            )

        select.callback = editGoodsOnSelect
        view.add_item(select)
        embed = discord.Embed(
            title="確認・編集する商品を選択してください", colour=discord.Colour.pink()
        )
        await interaction.followup.send(embed=embed, view=view)

    # @goodsGroup.command(name="remove", description="自販機の商品を削除します。")
    @app_commands.command(name="removegoods", description="自販機の商品を削除します。")
    @app_commands.autocomplete(_jihanki=JihankiService.getJihankiList)
    @app_commands.rename(_jihanki="自販機")
    @app_commands.describe(_jihanki="商品を削除したい自販機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def removeGoodsCommand(
        self,
        interaction: discord.Interaction,
        _jihanki: str,
    ):
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
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f'{good.name} ({good.price}円) {"(在庫無限)" if good.infinite else ""}',
                    description=good.description,
                    value=index,
                )
                for index, good in enumerate(jihanki.goods[0:20])
            ]
        )

        async def removeGoodsOnSelect(_interaction: discord.Interaction):
            await _interaction.response.defer(ephemeral=True)
            try:
                jihanki.goods.remove(jihanki.goods[int(_interaction.data["values"][0])])
                await JihankiService.editJihanki(jihanki, editGoods=True)

                embed = discord.Embed(
                    title="自販機から商品を削除しました",
                    colour=discord.Colour.green(),
                )
                await _interaction.followup.send(embed=embed, ephemeral=True)

                view = discord.ui.View(timeout=None)
                select = discord.ui.Select(
                    options=[
                        discord.SelectOption(
                            label=f'{good.name} ({good.price}円) {"(在庫無限)" if good.infinite else ""}',
                            description=good.description,
                            value=index,
                        )
                        for index, good in enumerate(jihanki.goods[0:20])
                    ]
                )

                select.callback = removeGoodsOnSelect
                view.add_item(select)
                embed = discord.Embed(
                    title="確認・編集する商品を選択してください",
                    colour=discord.Colour.pink(),
                )

                await interaction.edit_original_response(embed=embed, view=view)
            except Exception as e:
                embed = discord.Embed(
                    title="その商品はすでに削除済みです", colour=discord.Colour.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

        select.callback = removeGoodsOnSelect
        view.add_item(select)
        embed = discord.Embed(
            title="確認・編集する商品を選択してください", colour=discord.Colour.pink()
        )
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(JihankiEditCog(bot))
