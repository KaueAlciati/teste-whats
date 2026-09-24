from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.financial_profile import FinancialProfile
from backend.models.user import User


def mark_insights_stale(db: Session, *, user_id: int) -> bool:
    """Mark automatic insights stale without committing the caller transaction."""
    user = db.get(User, user_id)
    if user is None or not user.automatic_insights_enabled:
        return False

    profile = db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    if profile is None or profile.analysis_stale:
        return False

    profile.analysis_stale = True
    return True
