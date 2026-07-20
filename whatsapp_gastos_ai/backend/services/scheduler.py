from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Any

import psycopg2

from backend.services.whatsapp_service import enviar_mensagem_whatsapp

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover - fallback for environments without apscheduler
    BackgroundScheduler = None
    CronTrigger = None
    logger.warning("apscheduler não está disponível; lembretes agendados ficarão desativados neste ambiente.")


class _FallbackScheduler:
    def start(self) -> None:
        return None

    def add_job(self, *args: Any, **kwargs: Any) -> None:
        logger.warning("Scheduler desativado neste ambiente; job ignorado.")


scheduler = BackgroundScheduler() if BackgroundScheduler else _FallbackScheduler()
scheduler.start()


def _enviar_mensagem_sync(telefone: str, mensagem: str) -> None:
    asyncio.run(enviar_mensagem_whatsapp(telefone, mensagem))


def alerta_fatura():
    if not DATABASE_URL:
        return
    hoje = datetime.date.today()
    primeiro_dia_mes = hoje.replace(day=1)
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(valor) FROM fatura_cartao WHERE data_fim BETWEEN %s AND %s",
        (primeiro_dia_mes, primeiro_dia_mes + datetime.timedelta(days=30)),
    )
    total_fatura = cursor.fetchone()[0] or 0.0
    cursor.close()
    conn.close()
    if total_fatura > 0:
        telefone = os.getenv("WHATSAPP_NUMBER")
        if telefone:
            _enviar_mensagem_sync(telefone, f"💳 Sua fatura do cartão deste mês é R$ {total_fatura:.2f}.")


if BackgroundScheduler and CronTrigger:
    scheduler.add_job(alerta_fatura, "cron", day=1, hour=9)


def normalizar_cron(expr):
    partes = expr.strip().split()
    while len(partes) < 5:
        partes.append("*")
    return partes[:5]


def agendar_lembrete_cron(telefone: str, mensagem: str, cron_expr: str):
    if not CronTrigger:
        logger.warning("apscheduler indisponível; lembrete não foi agendado para %s.", telefone)
        return
    cron_parts = normalizar_cron(cron_expr)
    trigger = CronTrigger(
        minute=cron_parts[0],
        hour=cron_parts[1],
        day=cron_parts[2],
        month=cron_parts[3],
        day_of_week=cron_parts[4],
    )
    scheduler.add_job(
        _enviar_mensagem_sync,
        trigger=trigger,
        args=[telefone, mensagem],
        id=f"lembrete_{telefone}_{hash(mensagem)}",
        replace_existing=True,
    )


def carregar_lembretes_salvos():
    if not DATABASE_URL or not CronTrigger:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT telefone, mensagem, cron FROM lembretes")
    for telefone, mensagem, cron in cursor.fetchall():
        agendar_lembrete_cron(telefone, mensagem, cron)
    cursor.close()
    conn.close()


carregar_lembretes_salvos()
