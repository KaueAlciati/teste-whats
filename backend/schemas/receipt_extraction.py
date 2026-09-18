from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReceiptDocumentType = Literal[
    "pix_receipt",
    "bank_transfer_receipt",
    "payment_receipt",
    "purchase_receipt",
    "invoice_image",
    "unknown",
]

ReceiptDirection = Literal["outflow", "inflow", "unknown"]

ReceiptStatus = Literal[
    "completed",
    "pending",
    "scheduled",
    "cancelled",
    "refunded",
    "unknown",
]


class ReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: ReceiptDocumentType
    amount: str | None = None
    currency: str | None = None
    transaction_date: str | None = None
    transaction_time: str | None = None
    payer_name: str | None = None
    payer_institution: str | None = None
    recipient_name: str | None = None
    recipient_institution: str | None = None
    pix_key: str | None = None
    end_to_end_id: str | None = None
    description: str | None = None
    direction: ReceiptDirection
    category_suggestion: str | None = None
    status: ReceiptStatus
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    reason: str | None = None
