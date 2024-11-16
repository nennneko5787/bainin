import traceback
import subprocess

import discord
from discord.ext import commands

from .database import Database


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command("git_pull")
    async def gitPullCommand(self, ctx: commands.Context):
        cp = subprocess.run(["git", "pull"])
        if cp.returncode != 0:
            await ctx.reply("failed")
        else:
            await ctx.reply("success")

    @commands.command("load")
    async def cogLoadCommand(self, ctx: commands.Context, *, extension: str):
        try:
            await self.bot.load_extension(extension)
            await ctx.reply("success")
        except:
            traceback.print_exc()
            await ctx.reply("failed")

    @commands.command("reload")
    async def cogReloadCommand(self, ctx: commands.Context, *, extension: str):
        try:
            await self.bot.reload_extension(extension)
            await ctx.reply("success")
        except:
            traceback.print_exc()
            await ctx.reply("failed")

    @commands.command("check")
    async def checkCommand(self, ctx: commands.Context, service: str, userId: int):
        if ctx.author.id != 1048448686914551879:
            return

        row = await Database.pool.fetchrow(
            f"SELECT * FROM {service} WHERE id = $1", userId
        )

        if row:
            await ctx.reply(f"存在します\n```\nID: {row['id']}```")
        else:
            await ctx.reply("存在しません")

    @commands.command("dmsend")
    async def dmSendCommand(self, ctx: commands.Context, *, message: str):
        if ctx.author.id != 1048448686914551879:
            return

        _users = await Database.pool.fetch("SELECT owner_id FROM jihanki")

        jUsers = [user["owner_id"] for user in _users]

        _users = await Database.pool.fetch(
            "SELECT * FROM kyash"
        ) + await Database.pool.fetch("SELECT * FROM paypay")

        _users = [user["id"] for user in _users] + jUsers

        users = list(set(_users))

        successCount = 0
        failedCount = 0

        for u in users:
            user = await self.bot.fetch_user(u)
            print(
                f"username: {user.name} / userid: {user.id} / displayname: {user.display_name}"
            )
            try:
                await user.send(message, silent=True)
                successCount += 1
            except:
                traceback.print_exc()
                failedCount += 1

        embed = discord.Embed(
            title="DMを送り終わりました",
            description=f"成功: {successCount}\n失敗: {failedCount}",
            colour=discord.Colour.blurple(),
        )
        await ctx.reply(embed=embed)

    @commands.command("jsend")
    async def jSendCommand(self, ctx: commands.Context, *, message: str):
        if ctx.author.id != 1048448686914551879:
            return

        _users = await Database.pool.fetch("SELECT owner_id FROM jihanki")

        users = list(set([user["owner_id"] for user in _users]))

        successCount = 0
        failedCount = 0

        for u in users:
            user = await self.bot.fetch_user(u)
            print(
                f"username: {user.name} / userid: {user.id} / displayname: {user.display_name}"
            )
            try:
                await user.send(message, silent=True)
                successCount += 1
            except:
                traceback.print_exc()
                failedCount += 1
        embed = discord.Embed(
            title="DMを送り終わりました",
            description=f"成功: {successCount}\n失敗: {failedCount}",
            colour=discord.Colour.blurple(),
        )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
