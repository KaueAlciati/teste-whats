from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.user import User
from backend.schemas.insights import (
    DashboardInsightResponse,
    FinancialProfileResponse,
    FinancialProfileState,
    FinancialProfileWrite,
    InsightsAnalysisResponse,
)
from backend.services.financial_profile_service import (
    FinancialProfileAlreadyExistsError,
    create_financial_profile,
    get_financial_profile,
    update_financial_profile,
)
from backend.services.insights_service import (
    build_dashboard_insight,
    build_insights_analysis,
    financial_profile_response,
)


router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/profile", response_model=FinancialProfileState)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialProfileState:
    profile = get_financial_profile(db, user_id=current_user.id)
    return FinancialProfileState(
        onboarding_completed=bool(profile and profile.onboarding_completed),
        profile=financial_profile_response(profile) if profile else None,
    )


@router.post(
    "/profile",
    response_model=FinancialProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_profile(
    payload: FinancialProfileWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialProfileResponse:
    try:
        profile = create_financial_profile(
            db,
            user_id=current_user.id,
            data=payload,
        )
    except FinancialProfileAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    return financial_profile_response(profile)


@router.put("/profile", response_model=FinancialProfileResponse)
def put_profile(
    payload: FinancialProfileWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialProfileResponse:
    profile = get_financial_profile(db, user_id=current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil financeiro não encontrado",
        )
    updated = update_financial_profile(
        db,
        profile=profile,
        user_id=current_user.id,
        data=payload,
    )
    return financial_profile_response(updated)


@router.get("", response_model=InsightsAnalysisResponse)
def get_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightsAnalysisResponse:
    profile = _completed_profile(db, current_user.id)
    return build_insights_analysis(
        db,
        user=current_user,
        profile=profile,
    )


@router.post("/refresh", response_model=InsightsAnalysisResponse)
def refresh_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightsAnalysisResponse:
    profile = _completed_profile(db, current_user.id)
    return build_insights_analysis(
        db,
        user=current_user,
        profile=profile,
        force_refresh=True,
    )


@router.get("/summary", response_model=DashboardInsightResponse)
def dashboard_insight(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardInsightResponse:
    profile = get_financial_profile(db, user_id=current_user.id)
    return build_dashboard_insight(
        db,
        user_id=current_user.id,
        profile=profile,
    )


def _completed_profile(db: Session, user_id: int):
    profile = get_financial_profile(db, user_id=user_id)
    if profile is None or not profile.onboarding_completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conclua o onboarding financeiro antes de gerar a análise",
        )
    return profile
