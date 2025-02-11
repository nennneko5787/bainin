from pydantic import BaseModel, Field
from typing import Optional


class Good(BaseModel):
    name: str
    description: str
    price: int = Field(gt=-1)
    infinite: bool
    value: str
    emoji: Optional[str] = Field(None)
