from __future__ import annotations

import logging
from datetime import datetime, timedelta

from backend.services.db_init import conectar_bd

logger = logging.getLogger(__name__)


def salvar_fatura(descricao, valor, categoria, meio_pagamento, parcelas, schema):
    conn = conectar_bd()
    cursor = conn.cursor()
    data_compra = datetime.now().strftime("%Y-%m-%d")
    for i in range(parcelas):
        parcela_numero = f"{i + 1}/{parcelas}"
        data_fim = (datetime.now() + timedelta(days=30 * (i + 1))).date()
        cursor.execute(f"""
            INSERT INTO {schema}.fatura_cartao (descricao, valor, categoria, meio_pagamento, parcela, data_inicio, data_fim)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (descricao, valor / parcelas, categoria, meio_pagamento, parcela_numero, data_compra, data_fim))
    conn.commit()
    cursor.close()
    conn.close()


def salvar_gasto(descricao, valor, categoria, meio_pagamento, schema, parcelas=1):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO {schema}.gastos (descricao, valor, categoria, meio_pagamento, parcelas)
        VALUES (%s, %s, %s, %s, %s)
    """, (descricao, valor, categoria, meio_pagamento, parcelas))
    conn.commit()
    cursor.close()
    conn.close()


def calcular_total_gasto(schema):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(f"SELECT SUM(valor) FROM {schema}.gastos WHERE data >= date_trunc('month', CURRENT_DATE)")
    total = cursor.fetchone()[0] or 0.0
    cursor.close()
    conn.close()
    return total


def pagar_fatura(schema):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT descricao, valor, categoria, meio_pagamento FROM {schema}.fatura_cartao
        WHERE DATE_PART('month', data_fim) = DATE_PART('month', CURRENT_DATE)
          AND DATE_PART('year', data_fim) = DATE_PART('year', CURRENT_DATE)
    """)
    registros = cursor.fetchall()
    for descricao, valor, categoria, meio_pagamento in registros:
        cursor.execute(f"""
            INSERT INTO {schema}.gastos (descricao, valor, categoria, meio_pagamento, parcelas)
            VALUES (%s, %s, %s, %s, %s)
        """, (descricao, valor, categoria, meio_pagamento, 1))
    cursor.execute(f"DELETE FROM {schema}.fatura_cartao WHERE DATE_PART('month', data_fim) = DATE_PART('month', CURRENT_DATE)")
    conn.commit()
    cursor.close()
    conn.close()


def registrar_salario(mensagem, schema):
    try:
        valor = float(mensagem.split()[-1].replace(",", "."))
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(f"INSERT INTO {schema}.salario (valor, data) VALUES (%s, NOW())", (valor,))
        conn.commit()
        cursor.close()
        conn.close()
        return f"💰 Salário de R$ {valor:.2f} registrado com sucesso!"
    except Exception:
        logger.exception("Erro ao registrar salário.")
        return "❌ Erro ao registrar salário. Verifique o valor e tente novamente."


def listar_lembretes(telefone, schema):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, mensagem, cron FROM {schema}.lembretes WHERE telefone = %s", (telefone,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"id": row[0], "mensagem": row[1], "cron": row[2]} for row in rows]


def apagar_lembrete(telefone, lembrete_id, schema):
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {schema}.lembretes WHERE id = %s AND telefone = %s", (lembrete_id, telefone))
    sucesso = cursor.rowcount > 0
    conn.commit()
    cursor.close()
    conn.close()
    return sucesso
