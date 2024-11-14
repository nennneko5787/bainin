import random

import discord
from discord import app_commands
from discord.ext import commands


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
                value="PayPayやKyashのアカウントとリンクできます。",
            )
            .add_field(name="/proxy", value="使用するプロキシを設定・編集します。")
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
                name="/editgoods", value="自販機の商品の中身を確認・修正します。"
            ).add_field(
                name="/removegoods", value="自販機から商品を削除します。"
            ).add_field(
                name="/send",
                value="自販機を現在のチャンネル、または特定のチャンネルに送信します。",
            )
        else:
            embed.add_field(
                name="自販機機能はどこですか...?",
                value="このボットを**サーバーにインストール**する必要があります。\n[ここをクリックしてサーバーに導入できます。](https://discord.com/oauth2/authorize?client_id=1289535525681627156&permissions=264192&integration_type=0&scope=bot)",
                inline=False,
            )

        embed.add_field(
            name="PayPayやKyashのリンクが必要なときはどんなときですか？",
            value="PayPayやKyashのリンクが必要なときは、以下のようなときです。\n- 自販機を設置し、利益を得ようとするとき。\n- 本ボットを通じてPayPayやKyashを送金したり受け取ったりするとき。\n-# 自販機を利用する際には、アカウントのリンクは必要ありません(送金URLのみでできます)。",
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
