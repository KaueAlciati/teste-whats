"""Adiciona origem de transação importada por CSV.

Revision ID: 20260922_0009
Revises: 20260921_0008
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260922_0009"
down_revision: str | None = "20260921_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_SOURCE_CHECK = (
    "source IN ("
    "'whatsapp_text', 'whatsapp_audio', 'whatsapp_image', "
    "'whatsapp_document', 'web', 'dashboard_manual'"
    ")"
)
NEW_SOURCE_CHECK = (
    "source IN ("
    "'whatsapp_text', 'whatsapp_audio', 'whatsapp_image', "
    "'whatsapp_document', 'web', 'dashboard_manual', 'import_csv'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("financial_transactions") as batch_op:
        batch_op.drop_constraint(
            "ck_financial_transactions_source",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_financial_transactions_source",
            NEW_SOURCE_CHECK,
        )


def downgrade() -> None:
    op.execute(
        "UPDATE financial_transactions SET source = 'web' "
        "WHERE source = 'import_csv'"
    )
    with op.batch_alter_table("financial_transactions") as batch_op:
        batch_op.drop_constraint(
            "ck_financial_transactions_source",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_financial_transactions_source",
            OLD_SOURCE_CHECK,
        )
