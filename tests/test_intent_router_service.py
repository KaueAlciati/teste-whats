import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import IntentExample
from backend.schemas.natural_intent import (
    NaturalIntentDecision,
    NaturalIntentParameters,
)
from backend.services.intent_router_service import (
    route_deterministic_intent,
    route_natural_intent,
)


class IntentRouterServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.current_date = date(2026, 9, 23)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_real_phrases_route_to_expected_intents(self) -> None:
        cases = (
            ("qual minha maior despesa?", "consultar_maior_gasto"),
            ("com o que eu mais gastei?", "consultar_categoria_maior_gasto"),
            ("quanto gastei com gasolina?", "consultar_gasto_categoria"),
            ("me mostra os últimos 5 gastos", "consultar_ultimas_transacoes"),
            ("quanto gastei ontem?", "consultar_gastos_periodo"),
            ("quanto recebi esse mês?", "consultar_receitas_periodo"),
            ("como estão minhas finanças?", "analisar_financas"),
            ("o que posso melhorar?", "sugerir_melhorias_financeiras"),
            ("qual meta está mais perto?", "consultar_meta_mais_proxima"),
            ("como estão minhas metas?", "consultar_status_metas"),
            ("me mostra o extrato da meta teste", "extrato_meta"),
            ("o que já coloquei nessa meta?", "extrato_meta"),
        )
        for phrase, expected in cases:
            with self.subTest(phrase=phrase):
                decision = route_deterministic_intent(
                    phrase,
                    current_date=self.current_date,
                )
                self.assertIsNotNone(decision)
                self.assertEqual(decision.intent, expected)

    def test_abbreviations_and_transcription_variations(self) -> None:
        cases = (
            ("qnt gastei hj", "consultar_gastos_periodo"),
            ("onde q mais gastei", "consultar_maior_gasto"),
            ("me mostra os ultimos gasto", "consultar_ultimas_transacoes"),
            ("como ta minhas finança", "analisar_financas"),
            ("qual meta falta menos", "consultar_meta_mais_proxima"),
            ("extrato do test", "extrato_meta"),
        )
        for phrase, expected in cases:
            with self.subTest(phrase=phrase):
                decision = route_deterministic_intent(
                    phrase,
                    current_date=self.current_date,
                )
                self.assertIsNotNone(decision)
                self.assertEqual(decision.intent, expected)

    def test_ambiguous_largest_expense_requests_clarification(self) -> None:
        decision = route_deterministic_intent(
            "onde gastei mais esse mês?",
            current_date=self.current_date,
        )

        self.assertEqual(decision.confidence, 0.75)
        self.assertEqual(len(decision.candidates), 2)
        self.assertIn("despesa individual", decision.clarification_question)

    def test_explicit_financial_writes_are_not_classified_by_new_router(self) -> None:
        for phrase in (
            "gastei 50 de gasolina",
            "recebi 1000 de salário",
            "coloca 50 no teste",
            "me manda meu extrato do mês",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(
                    route_deterministic_intent(
                        phrase,
                        current_date=self.current_date,
                    )
                )

    def test_groq_fallback_uses_structured_output_and_active_examples(self) -> None:
        self.session.add(
            IntentExample(
                intent="consultar_maior_gasto",
                phrase="qual foi a compra mais pesada?",
                source="manual",
                active=True,
            )
        )
        self.session.commit()
        expected = NaturalIntentDecision(
            intent="consultar_maior_gasto",
            confidence=0.91,
            parameters=NaturalIntentParameters(period="current_month"),
            clarification_question=None,
            candidates=[],
        )
        client = MagicMock()
        client.responses.parse.return_value = SimpleNamespace(output_parsed=expected)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch(
            "backend.services.intent_router_service.OpenAI",
            return_value=client,
        ):
            outcome = route_natural_intent(
                self.session,
                text="qual foi a compra mais pesada?",
                current_date=self.current_date,
            )

        self.assertEqual(outcome.decision, expected)
        parse_call = client.responses.parse.call_args
        self.assertIs(parse_call.kwargs["text_format"], NaturalIntentDecision)
        self.assertEqual(parse_call.kwargs["temperature"], 0)
        self.assertIn("compra mais pesada", parse_call.kwargs["instructions"])

    def test_missing_provider_is_safe_and_does_not_invent_intent(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            outcome = route_natural_intent(
                self.session,
                text="frase completamente desconhecida",
                current_date=self.current_date,
            )

        self.assertIsNone(outcome.decision)
        self.assertEqual(outcome.failure_reason, "provider_unavailable")

    def test_invalid_structured_response_is_treated_as_unrecognized(self) -> None:
        client = MagicMock()
        client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch(
            "backend.services.intent_router_service.OpenAI",
            return_value=client,
        ):
            outcome = route_natural_intent(
                self.session,
                text="consulta que depende do classificador",
                current_date=self.current_date,
            )

        self.assertIsNone(outcome.decision)
        self.assertEqual(outcome.failure_reason, "invalid_json")


if __name__ == "__main__":
    unittest.main()
