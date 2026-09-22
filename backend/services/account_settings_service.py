from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.models.category import Category
from backend.models.financial_profile import FinancialProfile
from backend.models.financial_transaction import FinancialTransaction
from backend.models.goal import Goal
from backend.models.goal_context import GoalContext
from backend.models.goal_contribution import GoalContribution
from backend.models.pending_audio_confirmation import PendingAudioConfirmation
from backend.models.pending_receipt import PendingReceipt
from backend.models.user import User


def clear_financial_history(db: Session, *, user_id: int) -> None:
    """Remove only financial records owned by the authenticated user."""
    _delete_financial_records(db, user_id=user_id)

    profile = db.query(FinancialProfile).filter_by(user_id=user_id).one_or_none()
    if profile is not None:
        profile.analysis_cache = None
        profile.analysis_generated_at = None

    db.commit()


def delete_user_account(db: Session, *, user: User) -> None:
    """Physically remove one account after deleting all of its dependants."""
    user_id = user.id
    _delete_financial_records(db, user_id=user_id)
    db.execute(delete(FinancialProfile).where(FinancialProfile.user_id == user_id))
    db.delete(user)
    db.commit()


def _delete_financial_records(db: Session, *, user_id: int) -> None:
    # Explicit ordering keeps this safe even when a test/database connection
    # does not enforce ON DELETE CASCADE.
    for model in (
        PendingReceipt,
        PendingAudioConfirmation,
        GoalContext,
        GoalContribution,
        Goal,
        FinancialTransaction,
        Category,
    ):
        db.execute(delete(model).where(model.user_id == user_id))
