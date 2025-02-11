from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from .good import Good


class Jihanki(BaseModel):
    id: int
    createdAt: datetime = Field(datetime.now(), alias="created_at")
    name: str
    description: str = Field(None)
    goods: List[Good] = Field([])
    ownerId: int = Field(..., alias="owner_id")
    achievementChannelId: Optional[int] = Field(None, alias="achievement_channel_id")
    nsfw: bool
    freezed: Optional[str] = Field(None)
    shuffle: bool
