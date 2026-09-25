import logging
import os
from dataclasses import dataclass
from html import escape
from urllib.parse import quote, urlparse

import httpx


logger = logging.getLogger("uvicorn.error")

RESEND_EMAILS_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS = 15.0


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResendSettings:
    api_key: str
    from_email: str
    frontend_url: str


def get_resend_settings() -> ResendSettings:
    api_key = os.getenv("RESEND_API_KEY", "")
    from_email = _safe_env("RESEND_FROM_EMAIL")
    frontend_url = _safe_env("FRONTEND_URL").rstrip("/")

    if not api_key or not from_email or not frontend_url:
        raise EmailConfigurationError("Configuração de e-mail incompleta")
    if _contains_newline(api_key):
        raise EmailConfigurationError("RESEND_API_KEY inválida")
    if "@" not in from_email or _contains_newline(from_email):
        raise EmailConfigurationError("RESEND_FROM_EMAIL inválido")

    parsed_url = urlparse(frontend_url)
    is_local_http = (
        parsed_url.scheme == "http"
        and parsed_url.hostname in {"localhost", "127.0.0.1"}
    )
    if parsed_url.scheme != "https" and not is_local_http:
        raise EmailConfigurationError("FRONTEND_URL deve usar HTTPS")
    if not parsed_url.netloc or parsed_url.query or parsed_url.fragment:
        raise EmailConfigurationError("FRONTEND_URL inválida")

    return ResendSettings(
        api_key=api_key,
        from_email=from_email,
        frontend_url=frontend_url,
    )


def send_password_reset_email(
    recipient_email: str,
    token: str,
    *,
    settings: ResendSettings | None = None,
) -> None:
    resend_settings = settings or get_resend_settings()
    if "@" not in recipient_email or _contains_newline(recipient_email):
        raise EmailDeliveryError("Destinatário inválido")
    reset_url = (
        f"{resend_settings.frontend_url}/reset-password?token="
        f"{quote(token, safe='')}"
    )
    safe_url = escape(reset_url, quote=True)
    plain_content = (
        "FinControl AI\n\n"
        "Recebemos uma solicitação para redefinir sua senha.\n\n"
        f"Acesse este link: {reset_url}\n\n"
        "O link expira em breve e só pode ser usado uma vez. "
        "Se você não fez esta solicitação, ignore este e-mail."
    )
    html_content = (
        "<p><strong>FinControl AI</strong></p>"
        "<p>Recebemos uma solicitação para redefinir sua senha.</p>"
        f'<p><a href="{safe_url}">Definir nova senha</a></p>'
        "<p>O link expira em breve e só pode ser usado uma vez. "
        "Se você não fez esta solicitação, ignore este e-mail.</p>"
    )

    try:
        response = httpx.post(
            RESEND_EMAILS_URL,
            headers={
                "Authorization": f"Bearer {resend_settings.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"FinControl AI <{resend_settings.from_email}>",
                "to": [recipient_email],
                "subject": "Recuperação de senha — FinControl AI",
                "text": plain_content,
                "html": html_content,
            },
            timeout=RESEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise EmailDeliveryError("Não foi possível enviar o e-mail") from exc


def send_password_reset_email_safely(
    recipient_email: str,
    token: str,
    settings: ResendSettings,
) -> None:
    try:
        send_password_reset_email(
            recipient_email,
            token,
            settings=settings,
        )
    except (EmailConfigurationError, EmailDeliveryError) as exc:
        logger.error(
            "Falha ao enviar recuperação de senha: tipo=%s",
            type(exc).__name__,
        )


def _safe_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _contains_newline(value: str) -> bool:
    return "\r" in value or "\n" in value
