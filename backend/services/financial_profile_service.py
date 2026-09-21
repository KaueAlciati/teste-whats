from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.financial_profile import FinancialProfile
from backend.schemas.insights import FinancialProfileWrite


class FinancialProfileAlreadyExistsError(ValueError):
    pass


def get_financial_profile(
    db: Session,
    *,
    user_id: int,
) -> FinancialProfile | None:
    return db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )


def create_financial_profile(
    db: Session,
    *,
    user_id: int,
    data: FinancialProfileWrite,
) -> FinancialProfile:
    if get_financial_profile(db, user_id=user_id) is not None:
        raise FinancialProfileAlreadyExistsError("Perfil financeiro já existe")
    profile = FinancialProfile(
        user_id=user_id,
        **data.model_dump(),
        onboarding_completed=True,
    )
    db.add(profile)
    try:
        db.commit()
        db.refresh(profile)
        return profile
    except IntegrityError as exc:
        db.rollback()
        raise FinancialProfileAlreadyExistsError(
            "Perfil financeiro já existe"
        ) from exc


def update_financial_profile(
    db: Session,
    *,
    profile: FinancialProfile,
    user_id: int,
    data: FinancialProfileWrite,
) -> FinancialProfile:
    if profile.user_id != user_id:
        raise PermissionError("Perfil pertence a outro usuário")
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    profile.onboarding_completed = True
    profile.analysis_cache = None
    profile.analysis_generated_at = None
    db.commit()
    db.refresh(profile)
    return profile
