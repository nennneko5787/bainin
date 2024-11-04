import random

import discord
from discord.ext import commands
from discord import app_commands


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="ボットの使い方を確認できます。")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def helpCommand(self, interaction: discord.Interaction):
        embed = (
            discord.Embed(
                title="このボットの使い方",
                description="自販機も作れて送金・請求もDiscordでできるボットです。説明をよく読んでご利用ください～！\nサポートサーバー: https://discord.gg/2TfFUuY3RG",
                colour=random.choice(
                    [
                        discord.Colour.from_rgb(134, 206, 203),
                        discord.Colour.from_rgb(252, 245, 167),
                    ]
                ),
            )
            .set_author(
                name=interaction.client.user.display_name,
                url=interaction.client.user.display_avatar,
            )
            .add_field(
                name="/link",
                value="PayPayやKyashのアカウントとリンクできます。\nアカウントをリンクしないと本ボットをご利用いただくことはできません。",
            )
            .add_field(
                name="/check",
                value="PayPayやKyashを開かずとも、所持金を確認することができます。(本ボットではPayPayポイントはご利用いただけないため、所持していても表示されません。)",
            )
            .add_field(
                name="/remittance",
                value="Discordのユーザーを指定するだけで簡単に送金することができます。\n送信先のユーザーがPayPayかKyashのアカウントをリンクしている必要があります。",
            )
            .add_field(
                name="/claim",
                value="他のDiscordユーザーに簡単に請求することができるパネルを送信します。",
            )
            .set_footer(text="この埋め込みの色は2色のうちからランダムで変わります")
        )

        if interaction.is_guild_integration():
            embed.add_field(name="/make", value="自販機を作成します。").add_field(
                name="/edit", value="自販機を編集します。"
            ).add_field(name="/addgoods", value="自販機に商品を追加します。").add_field(
                name="/removegoods", value="自販機から商品を削除します。"
            ).add_field(
                name="/send",
                value="自販機を現在のチャンネル、または特定のチャンネルに送信します。",
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
