from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.models.category import Category
from backend.models.financial_profile import FinancialProfile
from backend.models.financial_transaction import FinancialTransaction
from backend.models.goal import Goal
from backend.models.goal_context import GoalContext
from backend.models.goal_contribution import GoalContribution
from backend.models.notification import Notification
from backend.models.pending_audio_confirmation import PendingAudioConfirmation
from backend.models.pending_receipt import PendingReceipt
from backend.models.user import User
from backend.services.attachment_service import (
    delete_stored_file,
    remove_user_attachments,
)


def clear_financial_history(db: Session, *, user_id: int) -> None:
    """Remove only financial records owned by the authenticated user."""
    attachment_keys = remove_user_attachments(db, user_id=user_id)
    _delete_financial_records(db, user_id=user_id)

    profile = db.query(FinancialProfile).filter_by(user_id=user_id).one_or_none()
    if profile is not None:
        profile.analysis_cache = None
        profile.analysis_generated_at = None

    db.commit()
    for storage_key in attachment_keys:
        delete_stored_file(storage_key)


def delete_user_account(db: Session, *, user: User) -> None:
    """Physically remove one account after deleting all of its dependants."""
    user_id = user.id
    attachment_keys = remove_user_attachments(db, user_id=user_id)
    _delete_financial_records(db, user_id=user_id)
    db.execute(delete(FinancialProfile).where(FinancialProfile.user_id == user_id))
    db.delete(user)
    db.commit()
    for storage_key in attachment_keys:
        delete_stored_file(storage_key)


def _delete_financial_records(db: Session, *, user_id: int) -> None:
    # Explicit ordering keeps this safe even when a test/database connection
    # does not enforce ON DELETE CASCADE.
    db.execute(
        delete(Notification).where(
            Notification.user_id == user_id,
            Notification.category == "financeiro",
        )
    )
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
