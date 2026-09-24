"""Adiciona dados supervisionados e contexto do roteador de intenções.

Revision ID: 20260923_0015
Revises: 20260923_0014
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0015"
down_revision: str | None = "20260923_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEED_EXAMPLES = (
    ("consultar_maior_gasto", "qual foi meu maior gasto?"),
    ("consultar_maior_gasto", "qual minha maior despesa?"),
    ("consultar_maior_gasto", "qual foi a coisa mais cara que paguei?"),
    ("consultar_categoria_maior_gasto", "com o que eu mais gastei?"),
    ("consultar_categoria_maior_gasto", "qual categoria eu mais gastei?"),
    ("consultar_categoria_maior_gasto", "onde está indo mais dinheiro?"),
    ("consultar_gasto_categoria", "quanto gastei com gasolina?"),
    ("consultar_gasto_categoria", "quanto foi de alimentação?"),
    ("consultar_gasto_categoria", "quanto gastei de mercado esse mês?"),
    ("consultar_ultimas_transacoes", "me mostra meus últimos gastos"),
    ("consultar_ultimas_transacoes", "últimos 5 gastos"),
    ("consultar_ultimas_transacoes", "mostra minhas últimas movimentações"),
    ("consultar_gastos_periodo", "quanto gastei hoje?"),
    ("consultar_gastos_periodo", "quanto gastei semana passada?"),
    ("consultar_gastos_periodo", "quanto gastei nos últimos 30 dias?"),
    ("consultar_receitas_periodo", "quanto recebi hoje?"),
    ("consultar_receitas_periodo", "quanto entrou essa semana?"),
    ("consultar_receitas_periodo", "quanto recebi no mês passado?"),
    ("analisar_financas", "como estão minhas finanças?"),
    ("analisar_financas", "tô gastando demais?"),
    ("analisar_financas", "como estou financeiramente?"),
    ("sugerir_melhorias_financeiras", "o que posso melhorar?"),
    ("sugerir_melhorias_financeiras", "onde posso economizar?"),
    ("sugerir_melhorias_financeiras", "como posso gastar menos?"),
    ("consultar_meta_mais_proxima", "qual meta está mais perto?"),
    ("consultar_meta_mais_proxima", "qual meta falta menos?"),
    ("consultar_meta_mais_proxima", "qual objetivo está quase concluído?"),
    ("consultar_status_metas", "como estão minhas metas?"),
    ("consultar_status_metas", "quanto falta pras minhas metas?"),
    ("consultar_status_metas", "me mostra meu progresso"),
    ("extrato_meta", "me mostra o extrato da meta teste"),
    ("extrato_meta", "quais aportes fiz no teste?"),
    ("extrato_meta", "histórico da meta viagem"),
)


def upgrade() -> None:
    intent_examples = op.create_table(
        "intent_examples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("phrase", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('seed', 'manual', 'reviewed')",
            name="ck_intent_examples_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intent_examples_intent",
        "intent_examples",
        ["intent"],
    )
    op.bulk_insert(
        intent_examples,
        [
            {
                "intent": intent,
                "phrase": phrase,
                "source": "seed",
                "active": True,
            }
            for intent, phrase in SEED_EXAMPLES
        ],
    )

    op.create_table(
        "unrecognized_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detected_intent", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "reviewed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("resolved_intent", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('whatsapp_text', 'whatsapp_audio')",
            name="ck_unrecognized_messages_source",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_unrecognized_messages_user_id",
        "unrecognized_messages",
        ["user_id"],
    )
    op.create_index(
        "ix_unrecognized_messages_reviewed_created",
        "unrecognized_messages",
        ["reviewed", "created_at"],
    )

    op.create_table(
        "intent_clarifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("unrecognized_message_id", sa.Integer(), nullable=True),
        sa.Column("original_message", sa.Text(), nullable=False),
        sa.Column("suggested_intent", sa.String(length=80), nullable=True),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["unrecognized_message_id"],
            ["unrecognized_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intent_clarifications_user_id",
        "intent_clarifications",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_intent_clarifications_expires_at",
        "intent_clarifications",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intent_clarifications_expires_at",
        table_name="intent_clarifications",
    )
    op.drop_index(
        "ix_intent_clarifications_user_id",
        table_name="intent_clarifications",
    )
    op.drop_table("intent_clarifications")
    op.drop_index(
        "ix_unrecognized_messages_reviewed_created",
        table_name="unrecognized_messages",
    )
    op.drop_index(
        "ix_unrecognized_messages_user_id",
        table_name="unrecognized_messages",
    )
    op.drop_table("unrecognized_messages")
    op.drop_index("ix_intent_examples_intent", table_name="intent_examples")
    op.drop_table("intent_examples")
