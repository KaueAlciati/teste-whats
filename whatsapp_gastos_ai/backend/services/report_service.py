from __future__ import annotations

import calendar
import logging
import re
import tempfile
import textwrap
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from backend.services.db_init import conectar_bd

logger = logging.getLogger(__name__)

UTC_MINUS_3 = timezone(timedelta(hours=-3))


def _periodo_padrao(
    periodo: str | None,
    *,
    inicio: date | datetime | None = None,
    fim: date | datetime | None = None,
) -> tuple[datetime, datetime, str]:
    hoje = datetime.now(UTC_MINUS_3).date()
    periodo_normalizado = (periodo or "current_month").strip().lower()

    if inicio and fim:
        inicio_date = inicio.date() if isinstance(inicio, datetime) else inicio
        fim_date = fim.date() if isinstance(fim, datetime) else fim
        label = f"{inicio_date.strftime('%d/%m/%Y')} a {fim_date.strftime('%d/%m/%Y')}"
        return (
            datetime.combine(inicio_date, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim_date, time.max, tzinfo=UTC_MINUS_3),
            label,
        )

    if periodo_normalizado in {"current_month", "this_month", "month", "mes atual", "mês atual", "today", "hoje"}:
        if periodo_normalizado == "today":
            inicio_date = fim_date = hoje
            label = hoje.strftime("%d/%m/%Y")
        else:
            inicio_date = hoje.replace(day=1)
            ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
            fim_date = hoje.replace(day=ultimo_dia)
            label = hoje.strftime("%m/%Y")
    elif periodo_normalizado in {"last_month", "previous_month", "mês passado", "mes passado", "último mês", "ultimo mês"}:
        primeiro_mes_atual = hoje.replace(day=1)
        ultimo_dia_mes_passado = primeiro_mes_atual - timedelta(days=1)
        inicio_date = ultimo_dia_mes_passado.replace(day=1)
        fim_date = ultimo_dia_mes_passado
        label = inicio_date.strftime("%m/%Y")
    elif periodo_normalizado in {"current_year", "this_year", "ano atual", "esse ano", "este ano"}:
        inicio_date = date(hoje.year, 1, 1)
        fim_date = date(hoje.year, 12, 31)
        label = str(hoje.year)
    elif periodo_normalizado == "yesterday":
        inicio_date = fim_date = hoje - timedelta(days=1)
        label = inicio_date.strftime("%d/%m/%Y")
    elif re.match(r"^\d{4}-\d{2}$", periodo_normalizado):
        ano, mes = map(int, periodo_normalizado.split("-"))
        inicio_date = date(ano, mes, 1)
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        fim_date = date(ano, mes, ultimo_dia)
        label = f"{mes:02d}/{ano}"
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", periodo_normalizado):
        inicio_date = fim_date = datetime.strptime(periodo_normalizado, "%Y-%m-%d").date()
        label = inicio_date.strftime("%d/%m/%Y")
    else:
        inicio_date = hoje.replace(day=1)
        ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
        fim_date = hoje.replace(day=ultimo_dia)
        label = hoje.strftime("%m/%Y")

    inicio_dt = datetime.combine(inicio_date, time.min, tzinfo=UTC_MINUS_3)
    fim_dt = datetime.combine(fim_date, time.max, tzinfo=UTC_MINUS_3)
    return inicio_dt, fim_dt, label


def _escape_pdf_text(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(texto: str, largura: int = 92) -> list[str]:
    linhas: list[str] = []
    for bloco in (texto or "").splitlines():
        if not bloco.strip():
            linhas.append("")
            continue
        quebradas = textwrap.wrap(bloco, width=largura, break_long_words=False, break_on_hyphens=False)
        linhas.extend(quebradas or [""])
    return linhas


def _chunk_lines(lines: list[str], chunk_size: int) -> list[list[str]]:
    return [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)] or [["Sem lançamentos no período."]]


def _build_pdf(pages: list[list[str]]) -> bytes:
    total_pages = len(pages) or 1
    total_objects = 3 + total_pages * 2  # catalog, pages, font, (page+content)*n
    objects: dict[int, bytes] = {}

    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for index, page_lines in enumerate(pages or [["Sem lançamentos no período."]], start=0):
        page_obj = 4 + index * 2
        content_obj = 5 + index * 2
        content_parts = ["BT", "/F1 12 Tf", "50 800 Td", "14 TL"]
        first_line = True
        for line in page_lines:
            safe = _escape_pdf_text(line if line else " ")
            if first_line:
                content_parts.append(f"({safe}) Tj")
                first_line = False
            else:
                content_parts.append("T*")
                content_parts.append(f"({safe}) Tj")
        content_parts.append("ET")
        content_stream = "\n".join(content_parts).encode("utf-8")
        objects[content_obj] = (
            b"<< /Length "
            + str(len(content_stream)).encode("ascii")
            + b" >>\nstream\n"
            + content_stream
            + b"\nendstream"
        )
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode("utf-8")

    kids = " ".join(f"{4 + index * 2} 0 R" for index in range(total_pages))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {total_pages} >>".encode("utf-8")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    offsets = [0] * (total_objects + 1)
    for obj_num in range(1, total_objects + 1):
        offsets[obj_num] = len(pdf)
        pdf.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        pdf.extend(objects.get(obj_num, b"<<>>"))
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {total_objects + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def gerar_pdf_financeiro(
    schema: str,
    periodo: str | None = None,
    *,
    inicio: date | datetime | None = None,
    fim: date | datetime | None = None,
) -> dict[str, str]:
    inicio_dt, fim_dt, label_periodo = _periodo_padrao(periodo, inicio=inicio, fim=fim)
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT descricao, valor, categoria, meio_pagamento, data
        FROM {schema}.gastos
        WHERE data >= %s AND data <= %s
        ORDER BY data ASC
        """,
        (inicio_dt, fim_dt),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    gastos = [
        {
            "descricao": row[0] or "",
            "valor": float(row[1] or 0),
            "categoria": row[2] or "geral",
            "meio_pagamento": row[3] or "não informado",
            "data": row[4],
        }
        for row in rows
    ]

    total = sum(item["valor"] for item in gastos)
    categorias = Counter(item["categoria"] for item in gastos)
    meios = Counter(item["meio_pagamento"] for item in gastos)

    linhas: list[str] = [
        "Relatório financeiro",
        f"Período: {label_periodo}",
        f"Total de gastos: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "",
        "Categorias:",
    ]
    if categorias:
        linhas.extend([f"- {categoria}: {quantidade}" for categoria, quantidade in categorias.items()])
    else:
        linhas.append("- Nenhum gasto registrado.")
    linhas.append("")
    linhas.append("Meios de pagamento:")
    if meios:
        linhas.extend([f"- {meio}: {quantidade}" for meio, quantidade in meios.items()])
    else:
        linhas.append("- Nenhum gasto registrado.")

    linhas.append("")
    linhas.append("Lançamentos:")
    if gastos:
        for item in gastos:
            data_fmt = item["data"].strftime("%d/%m/%Y") if hasattr(item["data"], "strftime") else str(item["data"])
            valor_fmt = f"R$ {item['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            linhas.append(f"- {data_fmt} | {valor_fmt} | {item['categoria']} | {item['meio_pagamento']} | {item['descricao']}")
    else:
        linhas.append("- Nenhum lançamento encontrado no período.")

    paginado = [_wrap_lines(linha) if isinstance(linha, str) else linha for linha in linhas]
    linhas_plana: list[str] = []
    for item in paginado:
        linhas_plana.extend(item if isinstance(item, list) else [str(item)])
    pages = _chunk_lines(linhas_plana, 45)
    pdf_bytes = _build_pdf(pages)

    arquivo_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix=f"relatorio_financeiro_{schema}_")
    try:
        arquivo_temp.write(pdf_bytes)
        arquivo_temp.flush()
    finally:
        arquivo_temp.close()

    documento_nome = f"relatorio_financeiro_{label_periodo.replace('/', '-')}.pdf"
    logger.info("PDF financeiro gerado: %s", arquivo_temp.name)
    return {"path": arquivo_temp.name, "name": documento_nome, "period_label": label_periodo, "total": f"{total:.2f}"}
