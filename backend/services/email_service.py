import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from urllib.parse import quote, urlparse


logger = logging.getLogger("uvicorn.error")


class EmailConfigurationError(RuntimeError):
    pass


class EmailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    frontend_url: str


def get_smtp_settings() -> SMTPSettings:
    host = _safe_env("SMTP_HOST")
    username = _safe_env("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD", "")
    from_email = _safe_env("SMTP_FROM_EMAIL")
    frontend_url = _safe_env("FRONTEND_URL").rstrip("/")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise EmailConfigurationError("SMTP_PORT inválida") from exc

    if not host or not username or not password or not from_email or not frontend_url:
        raise EmailConfigurationError("Configuração de e-mail incompleta")
    if not 1 <= port <= 65535:
        raise EmailConfigurationError("SMTP_PORT inválida")
    if "@" not in from_email or _contains_newline(from_email):
        raise EmailConfigurationError("SMTP_FROM_EMAIL inválido")
    if any(_contains_newline(value) for value in (host, username)):
        raise EmailConfigurationError("Configuração de e-mail inválida")

    parsed_url = urlparse(frontend_url)
    is_local_http = (
        parsed_url.scheme == "http"
        and parsed_url.hostname in {"localhost", "127.0.0.1"}
    )
    if parsed_url.scheme != "https" and not is_local_http:
        raise EmailConfigurationError("FRONTEND_URL deve usar HTTPS")
    if not parsed_url.netloc or parsed_url.query or parsed_url.fragment:
        raise EmailConfigurationError("FRONTEND_URL inválida")

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        frontend_url=frontend_url,
    )


def send_password_reset_email(
    recipient_email: str,
    token: str,
    *,
    settings: SMTPSettings | None = None,
) -> None:
    smtp_settings = settings or get_smtp_settings()
    if "@" not in recipient_email or _contains_newline(recipient_email):
        raise EmailDeliveryError("Destinatário inválido")
    reset_url = (
        f"{smtp_settings.frontend_url}/reset-password?token="
        f"{quote(token, safe='')}"
    )
    safe_url = escape(reset_url, quote=True)
    message = EmailMessage()
    message["Subject"] = "Redefinição de senha — FinControl AI"
    message["From"] = formataddr(("FinControl AI", smtp_settings.from_email))
    message["To"] = recipient_email
    message.set_content(
        "Recebemos uma solicitação para redefinir sua senha do FinControl AI.\n\n"
        f"Acesse este link: {reset_url}\n\n"
        "O link expira em breve e só pode ser usado uma vez. "
        "Se você não fez esta solicitação, ignore este e-mail."
    )
    message.add_alternative(
        "<p>Recebemos uma solicitação para redefinir sua senha do "
        "<strong>FinControl AI</strong>.</p>"
        f'<p><a href="{safe_url}">Definir nova senha</a></p>'
        "<p>O link expira em breve e só pode ser usado uma vez. "
        "Se você não fez esta solicitação, ignore este e-mail.</p>",
        subtype="html",
    )

    try:
        with smtplib.SMTP(
            smtp_settings.host,
            smtp_settings.port,
            timeout=15,
        ) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(smtp_settings.username, smtp_settings.password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Não foi possível enviar o e-mail") from exc


def send_password_reset_email_safely(
    recipient_email: str,
    token: str,
    settings: SMTPSettings,
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
