from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImportColumnMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date_column: str = Field(min_length=1)
    description_column: str = Field(min_length=1)
    amount_column: str | None = None
    type_column: str | None = None
    credit_column: str | None = None
    debit_column: str | None = None

    @model_validator(mode="after")
    def require_amount_source(self) -> "ImportColumnMapping":
        if self.amount_column is None and not (
            self.credit_column or self.debit_column
        ):
            raise ValueError(
                "Mapeie a coluna de valor ou ao menos uma coluna de crédito/débito"
            )
        return self


class ImportPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5 * 1024 * 1024)
    mapping: ImportColumnMapping | None = None


class ImportPreviewRow(BaseModel):
    id: int
    line_number: int
    date: date | None
    description: str
    amount: float | None
    type: Literal["income", "expense"] | None
    category: str | None
    category_source: Literal["rule", "fallback", "none"]
    status: Literal["ready", "possible_duplicate", "invalid"]
    error_reason: str | None = None


class ImportPreviewResponse(BaseModel):
    filename: str
    source: Literal["csv"] = "csv"
    delimiter: Literal[",", ";"]
    columns: list[str]
    mapping_required: bool
    mapping: ImportColumnMapping | None
    sample_rows: list[dict[str, str]]
    total: int
    ready: int
    possible_duplicates: int
    invalid: int
    rows: list[ImportPreviewRow]


class ImportConfirmRow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: date
    description: str = Field(min_length=1, max_length=255)
    amount: float = Field(gt=0)
    type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=80)
    allow_duplicate: bool = False


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ImportConfirmRow] = Field(min_length=1, max_length=5000)


class ImportConfirmResponse(BaseModel):
    status: Literal["success"] = "success"
    imported: int
    skipped_duplicates: int
