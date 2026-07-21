from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend.services.dashboard_service import build_dashboard_section, build_dashboard_snapshot
from backend.services.web_auth_service import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    SESSION_COOKIE,
    authenticate_web_user,
    bootstrap_web_admin,
    build_avatar_label,
    fetch_user_by_id,
    get_user_from_access_token,
    refresh_session,
    revoke_session,
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


@page_router.get("/dashboard")
async def dashboard_page(request: Request):
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        return RedirectResponse(url="/login", status_code=302)
    try:
        get_user_from_access_token(access_token)
        return _frontend_file("dashboard.html")
    except Exception:
        return RedirectResponse(url="/login", status_code=302)


@page_router.get("/index.html")
async def index_page(request: Request):
    return await root(request)


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
