import asyncio
import os
import traceback

import discord
import dotenv
import orjson
from cryptography.fernet import Fernet
from discord import app_commands
from discord.ext import commands
from snowflake import SnowflakeGenerator

from .database import Database

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


class AddGoodsModal(discord.ui.Modal, title="商品を追加"):
    def __init__(
        self,
        jihanki: int,
        name: str,
        description: str,
        price: int,
        infinite: bool = False,
        title="商品を追加",
    ):
        super().__init__(title=title)
        self.jihanki = jihanki
        self.name = name
        self.description = description
        self.price = price
        self.infinite = infinite
        self.goodsValue = discord.ui.TextInput(
            label=f'"{name}"の中身',
            style=discord.TextStyle.long,
            placeholder="内容をここに入力",
        )
        self.add_item(self.goodsValue)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        jihanki = await Database.pool.fetchrow(
            "SELECT * FROM jihanki WHERE id = $1", self.jihanki
        )
        if jihanki["owner_id"] != interaction.user.id:
            embed = discord.Embed(
                title="その自販機はあなたのものではありません",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])
        goods.append(
            {
                "name": self.name,
                "description": self.description,
                "price": self.price,
                "infinite": self.infinite,
                "value": cipherSuite.encrypt(self.goodsValue.value.encode()).decode(),
            }
        )
        await Database.pool.execute(
            "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
            orjson.dumps(goods).decode(),
            jihanki["id"],
        )
        embed = discord.Embed(
            title="自販機に商品を追加しました", colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "エラーです！ごめんなさい！", ephemeral=True
        )

        # Make sure we know what the error actually is
        traceback.print_exception(type(error), error, error.__traceback__)


class JihankiEditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="make", description="自販機を作成します。")
    @app_commands.describe(
        name="自販機の名前",
        description="自販機の説明",
        achievement="実績チャンネル",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def makeCommand(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        achievement: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        gen = SnowflakeGenerator(39)
        id = next(gen)
        await Database.pool.execute(
            "INSERT INTO jihanki (id, name, description, owner_id, achievement_channel_id) VALUES ($1, $2, $3, $4, $5)",
            id,
            name,
            description,
            interaction.user.id,
            achievement.id,
        )
        embed = discord.Embed(
            title="自販機を作成しました",
            description="`/addgoods` コマンドで商品を追加できます",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

        commands = await self.bot.tree.fetch_commands()
        for cmd in commands:
            if cmd.name == "link":
                commandId = cmd.id

        embed = discord.Embed(
            title="⚠️注意",
            description=f"自販機を作るだけでは、実際に売上を上げることはできません！\n売上を上げたい場合、 </link:{commandId}> コマンドしてPayPayかKyashのアカウントをリンクする必要があります。\nわからないときはいつでも[サポートサーバー](https://discord.gg/2TfFUuY3RG)へどうぞ。",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

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

    @app_commands.command(name="edit", description="自販機を編集します。")
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(
        jihanki="編集したい自販機",
        name="自販機の名前",
        description="自販機の説明",
        achievement="実績チャンネル",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def editCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        name: str,
        description: str,
        achievement: discord.TextChannel = None,
    ):
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
        await Database.pool.execute(
            "UPDATE ONLY jihanki SET name = $1, description = $2, achievement_channel_id = $3 WHERE id = $4",
            name,
            description,
            achievement.id,
            jihanki["id"],
        )
        embed = discord.Embed(
            title="自販機を編集しました", colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="addgoods", description="自販機に商品を追加します。")
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(
        jihanki="商品を追加したい自販機",
        name="商品の名前",
        description="商品の説明",
        price="商品の価格",
        infinite="在庫無限",
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def addGoodsCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        name: str,
        description: str,
        price: app_commands.Range[int, 0],
        infinite: bool = False,
    ):
        await interaction.response.send_modal(
            AddGoodsModal(int(jihanki), name, description, price, infinite)
        )

    class EditGoodModal(discord.ui.Modal):
        def __init__(
            self,
            jihanki: dict,
            goods: dict,
            select: int,
            interaction: discord.Interaction,
        ):
            super().__init__(title=f'{goods[select]["name"]} を編集')

            self.jihanki: dict = jihanki
            self.goods: dict = goods
            self.select: int = select
            self.interaction: discord.Interaction = interaction

            self.name = discord.ui.TextInput(
                label="商品の名前",
                placeholder="愛情",
                default=self.goods[self.select]["name"],
            )
            self.add_item(self.name)

            self.description = discord.ui.TextInput(
                label="商品の説明",
                placeholder="私の愛情を受け取ることができます",
                default=self.goods[self.select]["description"],
            )
            self.add_item(self.description)

            self.price = discord.ui.TextInput(
                label="価格",
                placeholder="数字以外受け付けません",
                default=self.goods[self.select]["price"],
            )
            self.add_item(self.price)

            self.value = discord.ui.TextInput(
                label="内容",
                placeholder="Chu!😘",
                default=cipherSuite.decrypt(self.goods[self.select]["value"]).decode(),
            )
            self.add_item(self.value)

        def convertToInteger(self, numeric: str) -> str | bool:
            try:
                return int(numeric)
            except ValueError:
                return False

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            self.goods[self.select]["name"] = self.name.value
            self.goods[self.select]["description"] = self.description.value
            price = self.convertToInteger(self.price.value)

            if (price is False) or (price < 0):
                embed = discord.Embed(
                    title="エラーが発生しました",
                    description="価格は0以上の整数でなければなりません",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            self.goods[self.select]["price"] = price
            self.goods[self.select]["value"] = cipherSuite.encrypt(
                self.value.value.encode()
            ).decode()

            goodsJson = orjson.dumps(self.goods).decode()
            await Database.pool.execute(
                "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                goodsJson,
                self.jihanki["id"],
            )

            await self.interaction.delete_original_response()

            embed = discord.Embed(
                title="編集しました！",
                colour=discord.Colour.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="editgoods", description="自販機の商品を編集・確認します。"
    )
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(jihanki="商品を編集したい自販機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def editGoodsCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
    ):
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
        goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f'{good["name"]} ({good["price"]}円) {"(在庫無限)" if good.get("infinite", False) else ""}',
                    description=good["description"],
                    value=index,
                )
                for index, good in enumerate(goods)
            ]
        )

        async def editGoodsOnSelect(_interaction: discord.Interaction):
            await _interaction.response.send_modal(
                self.EditGoodModal(
                    jihanki, goods, int(_interaction.data["values"][0]), interaction
                )
            )

        select.callback = editGoodsOnSelect
        view.add_item(select)
        embed = discord.Embed(
            title="確認・編集する商品を選択してください", colour=discord.Colour.pink()
        )
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="removegoods", description="自販機から商品を削除します。"
    )
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(jihanki="商品を削除したい自販機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def removeGoodsCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
    ):
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
        goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            options=[
                discord.SelectOption(
                    label=f'{good["name"]} ({good["price"]}円) {"(在庫無限)" if good.get("infinite", False) else ""}',
                    description=good["description"],
                    value=index,
                )
                for index, good in enumerate(goods)
            ]
        )

        async def removeGoodsOnSelect(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                goods.remove(goods[int(interaction.data["values"][0])])
                await Database.pool.execute(
                    "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2",
                    orjson.dumps(goods).decode(),
                    jihanki["id"],
                )

                await interaction.delete_original_response()

                embed = discord.Embed(
                    title="自販機から商品を削除しました",
                    colour=discord.Colour.green(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                traceback.print_exception(e)
                embed = discord.Embed(title="削除済みです", colour=discord.Colour.red())
                await interaction.followup.send(embed=embed, ephemeral=True)

        select.callback = removeGoodsOnSelect
        view.add_item(select)
        embed = discord.Embed(
            title="削除する商品を選択してください", colour=discord.Colour.red()
        )
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(JihankiEditCog(bot))
