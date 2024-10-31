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

from .database import Database

dotenv.load_dotenv()

cipherSuite = Fernet(os.getenv("fernet_key").encode())


class JihankiPanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            _interaction = interaction
            print(interaction.data)
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

                    if good["price"] == 0:
                        try:
                            embed = (
                                discord.Embed(title="商品が購入されました")
                                .set_thumbnail(url=interaction.user.display_icon.url)
                                .add_field(
                                    name="ユーザー",
                                    value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                                )
                                .add_field(
                                    name="商品",
                                    value=f'{good["name"]} ({good["price"]}円)',
                                )
                                .add_field(
                                    name="種別",
                                    value="<a:paypay:1301478001430626348> PayPay",
                                )
                            )
                            await self.bot.get_user(jihanki["owner_id"]).send(
                                embed=embed
                            )
                        except:
                            pass

                        embed = (
                            discord.Embed(title="購入明細書")
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

                        goods.remove(good)
                        await Database.pool.execute(
                            "UPDATE ONLY jihanki SET goods = $1",
                            orjson.dumps(goods).decode(),
                        )

                        embed = discord.Embed(
                            title=jihanki["name"],
                            description=f'{jihanki["description"]}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
                            colour=discord.Colour.og_blurple(),
                        )

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

                        await _interaction.message.edit(embed=embed, view=view)

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

                        else:
                            paypay = PayPay()
                            try:
                                await paypay.initialize(
                                    access_token=cipherSuite.decrypt(
                                        paypayAccount["access_token"]
                                    ).decode()
                                )
                            except:
                                pass
                                traceback.print_exc()
                                try:
                                    await paypay.token_refresh(
                                        cipherSuite.decrypt(
                                            paypayAccount["refresh_token"]
                                        ).decode()
                                    )
                                except:
                                    traceback.print_exc()
                                    embed = discord.Embed(
                                        title="PayPayでのログインに失敗しました。",
                                        description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                                        colour=discord.Colour.red(),
                                    )
                                    await interaction.followup.send(
                                        embed=embed, ephemeral=True
                                    )
                                    return

                            await paypay.get_balance()
                            if paypay.all_balance < good["price"]:
                                embed = discord.Embed(
                                    title="残高が足りません",
                                    description="PayPayをチャージしてください",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return

                            await paypay.send_money(
                                good["price"], ownerPaypayAccount["external_user_id"]
                            )

                            try:
                                embed = (
                                    discord.Embed(title="商品が購入されました")
                                    .set_thumbnail(
                                        url=interaction.user.display_icon.url
                                    )
                                    .add_field(
                                        name="ユーザー",
                                        value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                                    )
                                    .add_field(
                                        name="商品",
                                        value=f'{good["name"]} ({good["price"]}円)',
                                    )
                                    .add_field(
                                        name="種別",
                                        value="<a:paypay:1301478001430626348> PayPay",
                                    )
                                )
                                await self.bot.get_user(jihanki["owner_id"]).send(
                                    embed=embed
                                )
                            except:
                                pass

                            embed = (
                                discord.Embed(title="購入明細書")
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

                            goods.remove(good)
                            await Database.pool.execute(
                                "UPDATE ONLY jihanki SET goods = $1",
                                orjson.dumps(goods).decode(),
                            )

                            goods.remove(good)
                            await Database.pool.execute(
                                "UPDATE ONLY jihanki SET goods = $1",
                                orjson.dumps(goods).decode(),
                            )

                            embed = discord.Embed(
                                title=jihanki["name"],
                                description=f'{jihanki["description"]}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
                                colour=discord.Colour.og_blurple(),
                            )

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

                            await _interaction.message.edit(embed=embed, view=view)

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
                            "SELECT * FROM paypay WHERE id = $1", interaction.user.id
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
                        else:
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
                                    installation_uuid=str(ownerKyashAccount["installation_uuid"]),
                                )
                            except:
                                traceback.print_exc()
                                embed = discord.Embed(
                                    title="Kyashでのログインに失敗しました。",
                                    description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
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
                                    installation_uuid=str(kyashAccount["installation_uuid"]),
                                )
                            except:
                                traceback.print_exc()
                                embed = discord.Embed(
                                    title="Kyashでのログインに失敗しました。",
                                    description="アカウントが凍っているか、サーバー側でレートリミットがかかっている可能性があります",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return

                            await kyash.get_wallet()
                            if kyash.all_balance < good["price"]:
                                embed = discord.Embed(
                                    title="残高が足りません",
                                    description="Kyashをチャージしてください",
                                    colour=discord.Colour.red(),
                                )
                                await interaction.followup.send(
                                    embed=embed, ephemeral=True
                                )
                                return

                            await kyash.create_link(
                                amount=good["price"],
                                message=f'{good["name"]} を購入するため。',
                                is_claim=False,
                            )

                            await ownerKyash.link_recieve(url=kyash.created_link)

                            try:
                                embed = (
                                    discord.Embed(title="商品が購入されました")
                                    .set_thumbnail(
                                        url=interaction.user.display_icon.url
                                    )
                                    .add_field(
                                        name="ユーザー",
                                        value=f"{interaction.user.mention}\n`{interaction.user.name}`",
                                    )
                                    .add_field(
                                        name="商品",
                                        value=f'{good["name"]} ({good["price"]}円)',
                                    )
                                    .add_field(
                                        name="種別",
                                        value="<a:kyash:1301478014600609832> Kyash",
                                    )
                                )
                                await self.bot.get_user(jihanki["owner_id"]).send(
                                    embed=embed
                                )
                            except:
                                pass

                            embed = (
                                discord.Embed(title="購入明細書")
                                .add_field(
                                    name="商品",
                                    value=f'{good["name"]} ({good["price"]}円)',
                                )
                                .add_field(
                                    name="商品の内容",
                                    value=cipherSuite.decrypt(good["value"]).decode(),
                                )
                            )
                            await interaction.user.send(embed=embed)

                            goods.remove(good)
                            await Database.pool.execute(
                                "UPDATE ONLY jihanki SET goods = $1",
                                orjson.dumps(goods).decode(),
                            )

                            embed = discord.Embed(
                                title=jihanki["name"],
                                description=f'{jihanki["description"]}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
                                colour=discord.Colour.og_blurple(),
                            )

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

                            await _interaction.message.edit(embed=embed, view=view)

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

    @app_commands.command(name="send", description="自販機を送信します。")
    @app_commands.autocomplete(jihanki=getJihankiList)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
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
        embed = discord.Embed(
            title=jihanki["name"],
            description=f'{jihanki["description"]}\n\n-# 商品を購入する前に、<@1289535525681627156> からのDMを許可してください。\n-# 許可せずに商品を購入し、商品が受け取れなかった場合、責任を負いませんのでご了承ください。',
            colour=discord.Colour.og_blurple(),
        )

        goods: list[dict[str, str]] = orjson.loads(jihanki["goods"])

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

        await channel.send(embed=embed, view=view)

        embed = discord.Embed(
            title="自販機を送信しました",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(JihankiPanelCog(bot))
