import random

import discord
from discord import app_commands
from discord.ext import commands

from .edit import jihankiGroup, goodsGroup

from services.jihanki import JihankiService

from objects import Jihanki


class JihankiPanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
