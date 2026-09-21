import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import (
    Category,
    FinancialTransaction,
    Goal,
    GoalContribution,
    User,
)
from backend.schemas.financial_intent import FinancialIntent
from backend.services.financial_assistant_service import handle_financial_message
from backend.services.goal_service import create_goal


class GoalWhatsAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )()
        self.user = self._user("user@example.com", "5515999999999")
        self.other_user = self._user(
            "other@example.com",
            "5515888888888",
        )
        self.now = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=ZoneInfo("America/Sao_Paulo"),
        )

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_text_commands_create_select_contribute_query_and_complete(self) -> None:
        created = self._message(
            self.user,
            "criar meta Teste 1000",
            "wamid.goal-create",
        )
        selected = self._message(
            self.user,
            "meta teste",
            "wamid.goal-select",
        )
        contributed = self._message(
            self.user,
            "adiciona 100",
            "wamid.goal-add",
        )
        missing = self._message(
            self.user,
            "quanto falta?",
            "wamid.goal-missing",
        )
        progress = self._message(
            self.user,
            "progresso",
            "wamid.goal-progress",
        )
        statement = self._message(
            self.user,
            "extrato",
            "wamid.goal-statement",
        )
        goals = self._message(
            self.user,
            "minhas metas",
            "wamid.goal-list",
        )
        completed = self._message(
            self.user,
            "concluir meta",
            "wamid.goal-complete",
        )

        self.assertIn("criada", created)
        self.assertIn("selecionada", selected)
        self.assertIn("R$ 100,00", contributed)
        self.assertIn("R$ 900,00", missing)
        self.assertIn("10%", progress)
        self.assertIn("R$ 100,00", statement)
        self.assertIn("Teste", goals)
        self.assertIn("concluída", completed)

        goal = self.session.scalar(select(Goal).where(Goal.user_id == self.user.id))
        contributions = self.session.scalars(
            select(GoalContribution).where(
                GoalContribution.user_id == self.user.id
            )
        ).all()
        self.assertEqual(goal.status, "completed")
        self.assertEqual(len(contributions), 2)
        self.assertEqual(
            sum(float(contribution.amount) for contribution in contributions),
            1000.0,
        )
        self.assertTrue(
            all(
                contribution.source == "whatsapp_text"
                for contribution in contributions
            )
        )

    def test_audio_uses_same_goal_flow_and_audio_source(self) -> None:
        self._message(
            self.user,
            "criar meta Curso 500",
            "wamid.audio-goal-create",
            source="whatsapp_audio",
            audio_transcription="criar meta Curso 500",
        )

        response = self._message(
            self.user,
            "adiciona 50",
            "wamid.audio-goal-add",
            source="whatsapp_audio",
            audio_transcription="adiciona 50",
        )

        contribution = self.session.scalar(select(GoalContribution))
        self.assertIn('Entendi: "adiciona 50"', response)
        self.assertEqual(contribution.source, "whatsapp_audio")
        self.assertEqual(float(contribution.amount), 50.0)

    def test_goal_core_accepts_future_whatsapp_image_source(self) -> None:
        self._message(
            self.user,
            "criar meta Notebook 3000",
            "wamid.image-goal-create",
        )

        response = self._message(
            self.user,
            "adiciona 25",
            "wamid.image-goal-add",
            source="whatsapp_image",
        )

        contribution = self.session.scalar(select(GoalContribution))
        self.assertIn("R$ 25,00", response)
        self.assertEqual(contribution.source, "whatsapp_image")

    def test_selected_goal_context_expires_and_is_isolated(self) -> None:
        own_goal = create_goal(
            self.session,
            user_id=self.user.id,
            name="Reserva",
            target_amount=1000,
            target_date=None,
        )
        create_goal(
            self.session,
            user_id=self.other_user.id,
            name="Privada",
            target_amount=500,
            target_date=None,
        )

        selected = self._message(
            self.user,
            "meta Reserva",
            "wamid.context-select",
        )
        isolated = self._message(
            self.user,
            "meta Privada",
            "wamid.context-isolation",
        )
        expired = self._message(
            self.user,
            "adiciona 10",
            "wamid.context-expired",
            current_time=self.now + timedelta(minutes=31),
        )

        self.assertIn("selecionada", selected)
        self.assertIn("Não encontrei", isolated)
        self.assertIn("Selecione uma meta", expired)
        count = self.session.scalar(
            select(func.count(GoalContribution.id)).where(
                GoalContribution.goal_id == own_goal.id
            )
        )
        self.assertEqual(count, 0)

    def test_explicit_expense_is_not_confused_with_goal(self) -> None:
        self.session.add(
            Category(
                name="Outros",
                type="expense",
                user_id=None,
                is_default=True,
            )
        )
        self.session.commit()
        intent = FinancialIntent(
            action="create_expense",
            amount=50,
            description="gasolina",
            category="Outros",
            transaction_date="2026-09-21",
            payment_method=None,
            type="expense",
            period=None,
            needs_clarification=False,
            clarification_question=None,
            confidence=0.99,
        )

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=intent,
        ):
            response = self._message(
                self.user,
                "gastei 50 de gasolina",
                "wamid.normal-expense",
            )

        self.assertIn("Gasolina", response)
        self.assertEqual(
            self.session.scalar(select(func.count(FinancialTransaction.id))),
            1,
        )
        self.assertEqual(
            self.session.scalar(select(func.count(GoalContribution.id))),
            0,
        )

    def _message(
        self,
        user: User,
        text: str,
        message_id: str,
        *,
        source: str = "whatsapp_text",
        audio_transcription: str | None = None,
        current_time: datetime | None = None,
    ) -> str:
        response = handle_financial_message(
            self.session,
            user=user,
            text=text,
            whatsapp_message_id=message_id,
            current_date=date(2026, 9, 21),
            source=source,
            current_datetime=current_time or self.now,
            audio_transcription=audio_transcription,
        )
        self.assertIsNotNone(response)
        return response

    def _user(self, email: str, phone: str) -> User:
        user = User(
            name="Usuário",
            email=email,
            whatsapp_phone=phone,
            password_hash="$argon2id$test-hash",
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user


if __name__ == "__main__":
    unittest.main()
