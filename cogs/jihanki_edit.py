import asyncio
import os
import traceback

import discord
import dotenv
import orjson
from discord.ext import commands
from discord import app_commands
from aiokyasher import Kyash
from aiopaypaython import PayPay
from cryptography.fernet import Fernet
from snowflake import SnowflakeGenerator

from .database import Database

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


class AddGoodsModal(discord.ui.Modal, title="商品を追加"):
    def __init__(
        self, jihanki: int, name: str, description: str, price: int, title="商品を追加"
    ):
        super().__init__(title=title)
        self.jihanki = jihanki
        self.name = name
        self.description = description
        self.price = price
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
    @app_commands.describe(name="自販機の名前", description="自販機の説明")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def makeCommand(
        self, interaction: discord.Interaction, name: str, description: str
    ):
        await interaction.response.defer(ephemeral=True)
        gen = SnowflakeGenerator(39)
        id = next(gen)
        await Database.pool.execute(
            "INSERT INTO jihanki (id, name, description, owner_id) VALUES ($1, $2, $3, $4)",
            id,
            name,
            description,
            interaction.user.id,
        )
        embed = discord.Embed(
            title="自販機を作成しました",
            description="`/addgoods` コマンドで商品を追加できます",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed)

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
        jihanki="編集したい自販機", name="自販機の名前", description="自販機の説明"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def editCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        name: str,
        description: str,
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
            "UPDATE ONLY jihanki SET name = $1, description = $2 WHERE id = $3",
            name,
            description,
            jihanki["id"],
        )
        embed = discord.Embed(
            title="自販機を編集しました", colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="addgoods", description="自販機に商品を追加します。")
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(
        jihanki="商品を追加したい自販機", name="商品の名前", description="商品の説明"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def addGoodsCommand(
        self,
        interaction: discord.Interaction,
        jihanki: str,
        name: str,
        description: str,
        price: app_commands.Range[int, 0],
    ):
        await interaction.response.send_modal(
            AddGoodsModal(int(jihanki), name, description, price)
        )

    @app_commands.command(
        name="removegoods", description="自販機から商品を削除します。"
    )
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.describe(jihanki="商品を削除したい自販機")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
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
                    label=f'{good["name"]} ({good["price"]}円)',
                    description=good["description"],
                    value=index,
                )
                for index, good in enumerate(goods)
            ]
        )

        async def removeGoodsOnSelect(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                goods.remove(goods[select.options[0].value])
                await Database.pool.execute(
                    "UPDATE ONLY jihanki SET goods = $1", orjson.dumps(goods).decode()
                )
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
