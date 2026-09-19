import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import (  # noqa: F401
    Category,
    FinancialTransaction,
    PendingAudioConfirmation,
    User,
)
from backend.schemas.financial_intent import FinancialIntent
from backend.services.financial_assistant_service import (
    _message_already_processed,
    handle_financial_message,
)
from backend.services.pending_audio_confirmation_service import (
    create_pending_audio_confirmation,
)
from backend.services.user_service import get_or_create_whatsapp_user


class PendingAudioConfirmationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.session = self.session_factory()
        self._seed_categories()
        self.user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )
        self.current_date = date(2026, 9, 19)
        self.current_time = datetime(
            2026,
            9,
            19,
            10,
            0,
            tzinfo=timezone(timedelta(hours=-3)),
        )
        self.transcription = "Comprei 10 reais de chocolate"

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_positive_replies_confirm_original_audio(self) -> None:
        positive_replies = (
            "sim",
            "isso",
            "isso mesmo",
            "correto",
            "certo",
            "é isso",
            "exatamente",
            "pode",
            "pode registrar",
            "isso aí",
        )

        for index, reply in enumerate(positive_replies):
            with self.subTest(reply=reply):
                audio_message_id = f"audio-positive-{index}"
                self._ask_for_confirmation(audio_message_id)
                confirmed_intent = self._intent(confidence=0.98)

                with patch(
                    "backend.services.financial_assistant_service.interpret_financial_message",
                    return_value=confirmed_intent,
                ):
                    response = self._handle_text(
                        reply,
                        f"confirmation-{index}",
                    )

                transaction = self._transaction(audio_message_id)
                self.assertIsNotNone(transaction)
                self.assertEqual(transaction.type, "expense")
                self.assertEqual(transaction.amount, Decimal("10.00"))
                self.assertEqual(transaction.description, "Chocolate")
                self.assertEqual(transaction.source, "whatsapp_audio")
                self.assertIn("R$ 10,00", response)
                self.assertIsNone(self._latest_pending())

    def test_negative_reply_does_not_register(self) -> None:
        self._ask_for_confirmation("audio-negative")

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as ai_mock:
            response = self._handle_text("não", "negative-confirmation")

        ai_mock.assert_not_called()
        self.assertEqual(self._transaction_count(), 0)
        self.assertIsNone(self._latest_pending())
        self.assertIn("O que eu entendi errado", response)

    def test_correction_before_confirmation_registers_corrected_amount(self) -> None:
        self._ask_for_confirmation("audio-corrected")
        corrected_intent = self._intent(amount=20, confidence=0.98)

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=corrected_intent,
        ) as ai_mock:
            response = self._handle_text(
                "não, era 20",
                "correction-confirmation",
            )

        transaction = self._transaction("audio-corrected")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, Decimal("20.00"))
        self.assertEqual(self._transaction_count(), 1)
        self.assertEqual(
            ai_mock.call_args.kwargs["pending_audio_correction"],
            "não, era 20",
        )
        self.assertIn("R$ 20,00", response)

    def test_expired_pending_does_not_register(self) -> None:
        create_pending_audio_confirmation(
            self.session,
            user_id=self.user.id,
            original_whatsapp_message_id="audio-expired",
            transcription=self.transcription,
            current_time=self.current_time - timedelta(minutes=11),
        )

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as ai_mock:
            response = self._handle_text("isso", "expired-confirmation")

        ai_mock.assert_not_called()
        self.assertEqual(self._transaction_count(), 0)
        self.assertIn("expirou", response)
        self.assertIsNone(self._latest_pending())

    def test_other_user_cannot_confirm_pending_audio(self) -> None:
        self._ask_for_confirmation("audio-user-a")
        other_user = get_or_create_whatsapp_user(
            self.session,
            "5515888888888",
        )

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._intent(confidence=0.98),
        ):
            handle_financial_message(
                self.session,
                user=other_user,
                text="isso",
                whatsapp_message_id="user-b-confirmation",
                current_date=self.current_date,
                current_datetime=self.current_time + timedelta(minutes=1),
            )

        self.assertIsNone(self._transaction("audio-user-a"))
        self.assertIsNotNone(self._latest_pending())

    def test_pending_and_registered_audio_are_idempotent(self) -> None:
        self._ask_for_confirmation("audio-idempotent")

        with (
            patch(
                "backend.services.financial_assistant_service.engine",
                self.engine,
            ),
            patch(
                "backend.services.financial_assistant_service.SessionLocal",
                self.session_factory,
            ),
        ):
            self.assertTrue(_message_already_processed("audio-idempotent"))

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._intent(confidence=0.98),
        ):
            self._handle_text("isso", "idempotent-confirmation")
            duplicate_response = handle_financial_message(
                self.session,
                user=self.user,
                text=self.transcription,
                whatsapp_message_id="audio-idempotent",
                current_date=self.current_date,
                source="whatsapp_audio",
                current_datetime=self.current_time + timedelta(minutes=2),
                audio_transcription=self.transcription,
            )

        self.assertIsNone(duplicate_response)
        self.assertEqual(self._transaction_count(), 1)

    def _ask_for_confirmation(self, message_id: str) -> str | None:
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._intent(confidence=0.50),
        ):
            response = handle_financial_message(
                self.session,
                user=self.user,
                text=self.transcription,
                whatsapp_message_id=message_id,
                current_date=self.current_date,
                source="whatsapp_audio",
                current_datetime=self.current_time,
                audio_transcription=self.transcription,
            )
        self.assertIn("Foi isso mesmo?", response)
        return response

    def _handle_text(self, text: str, message_id: str) -> str | None:
        return handle_financial_message(
            self.session,
            user=self.user,
            text=text,
            whatsapp_message_id=message_id,
            current_date=self.current_date,
            current_datetime=self.current_time + timedelta(minutes=1),
        )

    def _transaction(self, message_id: str) -> FinancialTransaction | None:
        self.session.expire_all()
        return self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == message_id
            )
        )

    def _transaction_count(self) -> int:
        return self.session.scalar(select(func.count(FinancialTransaction.id))) or 0

    def _latest_pending(self) -> PendingAudioConfirmation | None:
        self.session.expire_all()
        return self.session.scalar(
            select(PendingAudioConfirmation)
            .where(PendingAudioConfirmation.user_id == self.user.id)
            .order_by(PendingAudioConfirmation.id.desc())
            .limit(1)
        )

    def _seed_categories(self) -> None:
        self.session.add_all(
            [
                Category(
                    name="Alimentação",
                    type="expense",
                    user_id=None,
                    is_default=True,
                ),
                Category(
                    name="Outros",
                    type="expense",
                    user_id=None,
                    is_default=True,
                ),
                Category(
                    name="Outros",
                    type="income",
                    user_id=None,
                    is_default=True,
                ),
            ]
        )
        self.session.commit()

    def _intent(
        self,
        *,
        amount: float = 10,
        confidence: float,
    ) -> FinancialIntent:
        return FinancialIntent(
            action="create_expense",
            amount=amount,
            description="Chocolate",
            category="Alimentação",
            transaction_date=self.current_date.isoformat(),
            payment_method=None,
            type=None,
            period=None,
            needs_clarification=False,
            clarification_question=None,
            confidence=confidence,
        )


if __name__ == "__main__":
    unittest.main()
