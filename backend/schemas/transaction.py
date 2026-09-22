from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TransactionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=255)
    amount: float = Field(gt=0)
    type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=80)
    date: date


class TransactionResponse(BaseModel):
    id: int
    description: str
    amount: float
    type: Literal["income", "expense"]
    category: str
    date: date
    source: str
    has_attachment: bool = False
