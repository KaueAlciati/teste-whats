import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.models import FinancialProfile, User
from backend.schemas.insights import FinancialProfileWrite
from backend.services.financial_profile_service import update_financial_profile
from backend.services.financial_service import (
    create_transaction,
    delete_transaction,
    update_transaction,
)
from backend.services.goal_contribution_service import add_goal_contribution
from backend.services.goal_service import create_goal, delete_goal, update_goal


class InsightsInvalidationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        with self.session_factory() as db:
            user = User(
                name="Usuário",
                email="user@example.com",
                whatsapp_phone="5515999999999",
                password_hash="$argon2id$test-hash",
                automatic_insights_enabled=True,
            )
            db.add(user)
            db.flush()
            profile = FinancialProfile(
                user_id=user.id,
                main_goal="organize_finances",
                investment_horizon="up_to_1_year",
                risk_profile="conservative",
                liquidity_need="high",
                has_debts=False,
                income_type="fixed",
                main_priority="organize_budget",
                onboarding_completed=True,
                analysis_stale=False,
            )
            db.add(profile)
            db.commit()
            self.user_id = user.id
            self.profile_id = profile.id

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_transactions_goals_contributions_and_profile_mark_analysis_stale(self) -> None:
        with self.session_factory() as db:
            transaction = create_transaction(
                db,
                user_id=self.user_id,
                type="expense",
                amount="10.00",
                description="Importado",
                transaction_date=date.today(),
                source="import_pdf",
            )
            self._assert_stale_and_reset(db)

            update_transaction(
                db,
                transaction=transaction,
                user_id=self.user_id,
                description="Importado corrigido",
            )
            self._assert_stale_and_reset(db)

            delete_transaction(
                db,
                transaction=transaction,
                user_id=self.user_id,
            )
            self._assert_stale_and_reset(db)

            goal = create_goal(
                db,
                user_id=self.user_id,
                name="Reserva",
                target_amount=Decimal("1000.00"),
                target_date=None,
            )
            self._assert_stale_and_reset(db)

            update_goal(
                db,
                goal=goal,
                user_id=self.user_id,
                changes={"name": "Reserva de emergência"},
            )
            self._assert_stale_and_reset(db)

            add_goal_contribution(
                db,
                goal_id=goal.id,
                user_id=self.user_id,
                amount="50.00",
                source="whatsapp_audio",
            )
            self._assert_stale_and_reset(db)

            delete_goal(db, goal=goal, user_id=self.user_id)
            self._assert_stale_and_reset(db)

            profile = db.get(FinancialProfile, self.profile_id)
            update_financial_profile(
                db,
                profile=profile,
                user_id=self.user_id,
                data=FinancialProfileWrite(
                    main_goal="emergency_reserve",
                    investment_horizon="one_to_three_years",
                    risk_profile="moderate",
                    liquidity_need="medium",
                    has_debts=False,
                    income_type="mixed",
                    main_priority="increase_savings",
                ),
            )
            self.assertTrue(profile.analysis_stale)

    def test_disabled_preference_does_not_mark_analysis_stale(self) -> None:
        with self.session_factory() as db:
            user = db.get(User, self.user_id)
            user.automatic_insights_enabled = False
            db.commit()

            create_transaction(
                db,
                user_id=self.user_id,
                type="income",
                amount="100.00",
                description="Recebimento por comprovante",
                transaction_date=date.today(),
                source="whatsapp_image",
            )

            profile = db.get(FinancialProfile, self.profile_id)
            self.assertFalse(profile.analysis_stale)

    def _assert_stale_and_reset(self, db) -> None:
        profile = db.get(FinancialProfile, self.profile_id)
        self.assertTrue(profile.analysis_stale)
        profile.analysis_stale = False
        db.commit()


if __name__ == "__main__":
    unittest.main()
