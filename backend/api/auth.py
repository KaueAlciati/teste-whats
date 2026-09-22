from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.models.user import User
from backend.schemas.auth import (
    DestructiveActionRequest,
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from backend.services.account_settings_service import (
    clear_financial_history,
    delete_user_account,
)
from backend.services.auth_service import (
    AuthConfigurationError,
    DuplicateEmailError,
    DuplicateWhatsAppPhoneError,
    InvalidCurrentPasswordError,
    InvalidCredentialsError,
    authenticate_user,
    change_user_password,
    create_access_token,
    decode_access_token,
    get_active_user_by_id,
    register_user,
    update_user_profile,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials)
        return get_active_user_by_id(db, user_id)
    except InvalidCredentialsError:
        raise _unauthorized() from None
    except AuthConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação indisponível",
        ) from None


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    try:
        return register_user(
            db,
            name=payload.name,
            email=str(payload.email),
            whatsapp_phone=payload.whatsapp_phone,
            password=payload.password.get_secret_value(),
        )
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    except DuplicateWhatsAppPhoneError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = authenticate_user(
            db,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
        )
        return TokenResponse(access_token=create_access_token(user))
    except InvalidCredentialsError:
        raise _unauthorized() from None
    except AuthConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação indisponível",
        ) from None


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/profile", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    try:
        return update_user_profile(
            db,
            user=current_user,
            name=payload.name,
            email=str(payload.email) if payload.email is not None else None,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        change_user_password(
            db,
            user=current_user,
            current_password=payload.current_password.get_secret_value(),
            new_password=payload.new_password.get_secret_value(),
        )
    except InvalidCurrentPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    return {"status": "ok"}


@router.delete("/financial-history")
def clear_history(
    payload: DestructiveActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.confirmation != "LIMPAR HISTÓRICO":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Digite "LIMPAR HISTÓRICO" para confirmar',
        )
    clear_financial_history(db, user_id=current_user.id)
    return {"status": "ok"}


@router.delete("/account")
def delete_account(
    payload: DestructiveActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.confirmation != "EXCLUIR CONTA":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Digite "EXCLUIR CONTA" para confirmar',
        )
    delete_user_account(db, user=current_user)
    return {"status": "ok"}
