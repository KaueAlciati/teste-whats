from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend.services.dashboard_service import build_dashboard_section, build_dashboard_snapshot
from backend.services.web_auth_service import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    SESSION_COOKIE,
    create_channel_link_code,
    authenticate_web_user,
    bootstrap_web_admin,
    build_avatar_label,
    auth_debug_summary,
    fetch_user_by_id,
    get_user_from_access_token,
    get_channel_link_status,
    register_web_user,
    request_email_verification_for_user,
    resolve_channel_link,
    refresh_session,
    revoke_session,
    unlink_channel,
    verify_email_token,
    safe_user_dict,
)

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

api_router = APIRouter(prefix="/api", tags=["web-api"])
page_router = APIRouter(tags=["frontend"])


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3)
    password: str = Field(min_length=4)
    remember_me: bool = False


class RegisterRequest(BaseModel):
    name: str = Field(min_length=3)
    email: str = Field(min_length=5)
    phone: str = Field(min_length=8)
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)
    accept_terms: bool = False


class VerifyEmailRequest(BaseModel):
    email: str = Field(min_length=5)
    token: str = Field(min_length=8)


def _api_success(data, message: str | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "message": message}, status_code=status_code)


def _api_error(message: str, status_code: int = 400, errors: dict | None = None) -> JSONResponse:
    return JSONResponse({"success": False, "data": None, "message": message, "errors": errors or {}}, status_code=status_code)


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    session_id: str,
    *,
    remember_me: bool,
    access_max_age: int,
    refresh_max_age: int,
) -> None:
    secure = False
    response.set_cookie(ACCESS_COOKIE, access_token, httponly=True, secure=secure, samesite="lax", max_age=access_max_age)
    response.set_cookie(REFRESH_COOKIE, refresh_token, httponly=True, secure=secure, samesite="lax", max_age=refresh_max_age)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, secure=secure, samesite="lax", max_age=refresh_max_age)


def _clear_auth_cookies(response: Response) -> None:
    for cookie in (ACCESS_COOKIE, REFRESH_COOKIE, SESSION_COOKIE):
        response.delete_cookie(cookie, path="/")


def _current_user_from_request(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    try:
        user = get_user_from_access_token(access_token)
        return user
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida.") from exc


def _frontend_file(name: str) -> FileResponse:
    file_path = FRONTEND_DIR / name
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Página não encontrada.")
    return FileResponse(file_path)


@page_router.get("/")
async def root(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if access_token:
        try:
            get_user_from_access_token(access_token)
            return RedirectResponse(url="/dashboard", status_code=302)
        except Exception:
            pass
    return RedirectResponse(url="/login", status_code=302)


@page_router.get("/login")
async def login_page():
    return _frontend_file("login.html")


@page_router.get("/register")
async def register_page():
    return _frontend_file("register.html")


@page_router.get("/dashboard")
async def dashboard_page(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        return RedirectResponse(url="/login", status_code=302)
    try:
        get_user_from_access_token(access_token)
        return _frontend_file("index.html")
    except Exception:
        return RedirectResponse(url="/login", status_code=302)


@page_router.get("/configuracoes")
async def configuracoes_page(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        return RedirectResponse(url="/login", status_code=302)
    try:
        get_user_from_access_token(access_token)
        return _frontend_file("profile.html")
    except Exception:
        return RedirectResponse(url="/login", status_code=302)


@page_router.get("/index.html")
async def index_page(request: Request):
    return await root(request)


@page_router.get("/profile.html")
async def profile_page(request: Request):
    return await configuracoes_page(request)


@page_router.get("/table.html")
async def table_page(request: Request):
    return _frontend_file("table.html")


@api_router.on_event("startup")
def _bootstrap_web_admin() -> None:
    try:
        bootstrap_web_admin()
    except Exception:
        logger.exception("Falha ao executar bootstrap do usuário web.")


@api_router.post("/auth/login")
async def login(request: Request, payload: LoginRequest):
    try:
        result = authenticate_web_user(
            payload.identifier.strip(),
            payload.password,
            remember_me=payload.remember_me,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as exc:
        return _api_error(str(exc), status_code=401)
    except Exception:
        logger.exception("Falha ao autenticar usuário web.")
        return _api_error("Não foi possível autenticar agora.", status_code=500)

    response = _api_success(
        {
            "user": {
                **safe_user_dict(result["user"]),
                "avatar_label": build_avatar_label(result["user"].nome, result["user"].email or result["user"].telefone),
            },
            "session_id": result["session_id"],
            "expires_in": result["expires_in"],
        },
        "Login realizado com sucesso.",
    )
    _set_auth_cookies(
        response,
        result["access_token"],
        result["refresh_token"],
        result["session_id"],
        remember_me=payload.remember_me,
        access_max_age=result["expires_in"],
        refresh_max_age=result["refresh_expires_in"],
    )
    return response


@api_router.post("/auth/register")
async def register(payload: RegisterRequest):
    if not payload.accept_terms:
        return _api_error("Você precisa aceitar os termos para criar a conta.", status_code=400)
    if payload.password != payload.confirm_password:
        return _api_error("A confirmação de senha não confere.", status_code=400)
    try:
        user = register_web_user(payload.name, payload.email, payload.phone, payload.password)
    except ValueError as exc:
        return _api_error(str(exc), status_code=400)
    except Exception:
        logger.exception("Falha ao registrar usuário web.")
        return _api_error("Não foi possível criar a conta agora.", status_code=500)

    return _api_success(
        {
            "user_id": user.id,
            "email": user.email,
            "phone": user.telefone,
        },
        "Conta criada com sucesso.",
    )


@api_router.get("/auth/debug")
async def auth_debug(request: Request, email: str | None = None, phone: str | None = None):
    if os.getenv("ENABLE_AUTH_DEBUG", "false").lower() != "true":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    _current_user_from_request(request)
    try:
        summary = auth_debug_summary(email=email, phone=phone)
    except ValueError as exc:
        return _api_error(str(exc), status_code=403)
    except Exception:
        logger.exception("Falha ao executar debug de autenticação.")
        return _api_error("Não foi possível executar o diagnóstico.", status_code=500)
    return _api_success(summary, "Diagnóstico de autenticação concluído.")


@api_router.post("/auth/refresh")
async def refresh(request: Request):
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        return _api_error("Sessão expirada.", status_code=401)
    try:
        result = refresh_session(refresh_token)
    except ValueError as exc:
        return _api_error(str(exc), status_code=401)
    except Exception:
        logger.exception("Falha ao renovar sessão web.")
        return _api_error("Não foi possível renovar a sessão.", status_code=500)

    response = _api_success(
        {
            "user": {
                **safe_user_dict(result["user"]),
                "avatar_label": build_avatar_label(result["user"].nome, result["user"].email or result["user"].telefone),
            },
            "session_id": result["session_id"],
            "expires_in": result["expires_in"],
        },
        "Sessão renovada.",
    )
    _set_auth_cookies(
        response,
        result["access_token"],
        result["refresh_token"],
        result["session_id"],
        remember_me=True,
        access_max_age=result["expires_in"],
        refresh_max_age=result["refresh_expires_in"],
    )
    return response


@api_router.post("/auth/request-email-verification")
async def request_email_verification(request: Request):
    user = _current_user_from_request(request)
    try:
        result = request_email_verification_for_user(user.id)
    except Exception:
        logger.exception("Falha ao solicitar verificação de e-mail.")
        return _api_error("Não foi possível gerar a verificação agora.", status_code=500)

    payload = {"expires_at": result["expires_at"].isoformat()}
    if os.getenv("APP_ENV", "development").lower() != "production":
        payload["debug_token"] = result["token"]
    return _api_success(payload, "Verificação de e-mail solicitada.")


@api_router.post("/auth/verify-email")
async def verify_email(payload: VerifyEmailRequest):
    try:
        verified = verify_email_token(payload.email, payload.token)
    except Exception:
        logger.exception("Falha ao verificar e-mail.")
        return _api_error("Não foi possível confirmar o e-mail agora.", status_code=500)
    if not verified:
        return _api_error("Token inválido ou expirado.", status_code=400)
    return _api_success({}, "E-mail confirmado com sucesso.")


@api_router.post("/auth/logout")
async def logout(request: Request):
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    session_id = request.cookies.get(SESSION_COOKIE)
    try:
        revoke_session(refresh_token=refresh_token, session_id=session_id)
    except Exception:
        logger.exception("Falha ao revogar sessão web.")
    response = _api_success({}, "Logout realizado.")
    _clear_auth_cookies(response)
    return response


@api_router.get("/integrations/telegram/status")
async def telegram_status(request: Request):
    user = _current_user_from_request(request)
    return _api_success(get_channel_link_status(user.id, "telegram"), None)


@api_router.post("/integrations/telegram/code")
async def telegram_link_code(request: Request):
    user = _current_user_from_request(request)
    status_info = get_channel_link_status(user.id, "telegram")
    if status_info.get("linked"):
        return _api_success(status_info, "Telegram já vinculado.")
    try:
        result = create_channel_link_code(user.id, "telegram")
    except Exception:
        logger.exception("Falha ao gerar código Telegram.")
        return _api_error("Não foi possível gerar o código agora.", status_code=500)
    return _api_success(
        {
            "linked": False,
            "pending": True,
            "code": result["code"],
            "expires_at": result["expires_at"].isoformat(),
            "channel": "telegram",
        },
        "Código gerado com sucesso.",
    )


@api_router.delete("/integrations/telegram")
async def telegram_unlink(request: Request):
    user = _current_user_from_request(request)
    try:
        removed = unlink_channel(user.id, "telegram")
    except Exception:
        logger.exception("Falha ao desvincular Telegram.")
        return _api_error("Não foi possível desvincular agora.", status_code=500)
    if not removed:
        return _api_error("Nenhum vínculo encontrado.", status_code=404)
    return _api_success({}, "Telegram desvinculado com sucesso.")


@api_router.get("/auth/me")
async def me(request: Request):
    user = _current_user_from_request(request)
    return _api_success({"user": {**safe_user_dict(user), "avatar_label": build_avatar_label(user.nome, user.email or user.telefone)}}, None)


@api_router.get("/dashboard/summary")
async def dashboard_summary(request: Request, period: str | None = None):
    user = _current_user_from_request(request)
    try:
        data = build_dashboard_snapshot(user, period)
    except ValueError as exc:
        return _api_error(str(exc), status_code=400)
    except Exception:
        logger.exception("Falha ao montar dashboard summary.")
        return _api_error("Não foi possível carregar o dashboard.", status_code=500)
    return _api_success(data, None)


@api_router.get("/dashboard/categories")
async def dashboard_categories(request: Request, period: str | None = None):
    user = _current_user_from_request(request)
    return _api_success(build_dashboard_section(user, "categories", period)["data"], None)


@api_router.get("/dashboard/cash-flow")
async def dashboard_cash_flow(request: Request, period: str | None = None):
    user = _current_user_from_request(request)
    return _api_success(build_dashboard_section(user, "cash-flow", period)["data"], None)


@api_router.get("/dashboard/recent-transactions")
async def dashboard_recent_transactions(request: Request, period: str | None = None):
    user = _current_user_from_request(request)
    return _api_success(build_dashboard_section(user, "recent-transactions", period)["data"], None)


@api_router.get("/dashboard/ai-summary")
async def dashboard_ai_summary(request: Request, period: str | None = None):
    user = _current_user_from_request(request)
    return _api_success(build_dashboard_section(user, "ai-summary", period)["data"], None)
