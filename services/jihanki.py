from typing import Optional, List

import discord
import orjson
from discord import app_commands

from objects import Jihanki

from .database import Database


class FailedToRequest(Exception):
    pass


class JihankiNotFoundException(Exception):
    pass


class JihankiService:
    """自販機を管理するサービス"""

    @classmethod
    async def makeJihanki(cls, jihanki: Jihanki) -> Jihanki:
        """自販機を作成します。

        Args:
            jihanki (Jihanki): 仮の自販機のインスタンス。

        Raises:
            FailedToRequest: 自販機の作成に失敗した場合。

        Returns:
            Jihanki: 完全な自販機のインスタンス。
        """
        row = await Database.pool.fetchrow(
            "INSERT INTO jihanki (id, name, description, owner_id, achievement_channel_id, nsfw, shuffle) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            jihanki.id,
            jihanki.name,
            jihanki.description,
            jihanki.ownerId,
            jihanki.achievementChannelId,
            jihanki.nsfw,
            jihanki.shuffle,
        )
        if not row:
            raise FailedToRequest()
        dictRow = dict(row)
        dictRow["goods"] = orjson.loads(dictRow["goods"])
        return Jihanki.model_validate(dictRow)

    @classmethod
    async def getJihanki(
        cls, userId: int, *, id: Optional[int] = None, name: Optional[str] = None
    ) -> Jihanki:
        """自販機を取得します。
        なお、IDと名前を両方指定するとエラーが発生します。

        Args:
            userId (int): 自販機を所有するユーザー。
            id (Optional[int], optional): 自販機のID。デフォルトはNoneです。
            name (Optional[str], optional): 自販機の名前。デフォルトはNoneです。

        Raises:
            ValueError: IDと名前を両方指定した場合。
            JihankiNotFoundException: 自販機が存在しない場合。

        Returns:
            Jihanki: 取得した自販機のインスタンス。
        """
        if not isinstance(id, int):
            id = int(id)
        if id and name:
            raise ValueError("IDと名前を両方指定することはできません。")
        if not name:
            row = await Database.pool.fetchrow(
                "SELECT * FROM jihanki WHERE id = $1", id
            )
        else:
            row = await Database.pool.fetchrow(
                "SELECT * FROM jihanki WHERE name LIKE $1 AND owner_id = $2 LIMIT 1",
                name,
                userId,
            )
        if not row:
            raise JihankiNotFoundException()
        dictRow = dict(row)
        dictRow["goods"] = orjson.loads(dictRow["goods"])
        return Jihanki.model_validate(dictRow)

    @classmethod
    async def getUserJihankis(cls, userId: int) -> List[Jihanki]:
        """自販機を取得します。
        なお、IDと名前を両方指定するとエラーが発生します。

        Args:
            userId (int): 自販機を所有するユーザー。

        Raises:
            ValueError: IDと名前を両方指定した場合。
            JihankiNotFoundException: 自販機が存在しない場合。

        Returns:
            Jihanki: 取得した自販機のインスタンス。
        """
        rows = await Database.pool.fetch(
            "SELECT * FROM jihanki WHERE owner_id = $1",
            userId,
        )
        if not rows:
            raise JihankiNotFoundException()
        jihankis = []
        for row in rows:
            dictRow = dict(row)
            dictRow["goods"] = orjson.loads(dictRow["goods"])
            jihankis.append(Jihanki.model_validate(dict(dictRow)))
        return jihankis

    @classmethod
    async def deleteJihanki(cls, jihanki: Jihanki) -> None:
        """自販機を削除します。

        Args:
            jihanki (Jihanki): 削除する自販機のインスタンス。
        """
        await Database.pool.execute(
            "DELETE FROM jihanki WHERE id = $1",
            jihanki.id,
        )

    @classmethod
    async def editJihanki(cls, jihanki: Jihanki, *, editGoods: bool = False) -> Jihanki:
        """自販機を編集します。

        Args:
            jihanki (Jihanki): 編集する自販機のインスタンス。
            editGoods (bool, optional): 商品を編集するかどうか。デフォルトはNoneです。

        Raises:
            FailedToRequest: リクエストに失敗した場合。

        Returns:
            Jihanki: 編集後の自販機のインスタンス。
        """
        if editGoods:
            goods = orjson.dumps([good.model_dump() for good in jihanki.goods]).decode()
            row = await Database.pool.fetchrow(
                "UPDATE ONLY jihanki SET goods = $1 WHERE id = $2 RETURNING *",
                goods,
                jihanki.id,
            )
        else:
            row = await Database.pool.fetchrow(
                "UPDATE ONLY jihanki SET name = $1, description = $2, achievement_channel_id = $3, nsfw = $4, shuffle = $5 WHERE id = $6 RETURNING *",
                jihanki.name,
                jihanki.description,
                jihanki.achievementChannelId,
                jihanki.nsfw,
                jihanki.shuffle,
                jihanki.id,
            )
        if not row:
            raise FailedToRequest()
        dictRow = dict(row)
        dictRow["goods"] = orjson.loads(dictRow["goods"])
        return Jihanki.model_validate(dictRow)

    @classmethod
    async def getJihankiList(
        cls,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        jihankiList = await cls.getUserJihankis(interaction.user.id)
        jihankis = []
        for jihanki in jihankiList:
            if jihanki.name.startswith(current):
                jihankis.append(
                    app_commands.Choice(
                        name=f"{jihanki.name}",
                        value=str(jihanki.id),
                    )
                )
        return jihankis
