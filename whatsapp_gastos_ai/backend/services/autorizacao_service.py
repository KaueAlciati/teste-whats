from __future__ import annotations

import os
import re
import unicodedata

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def _normalizar_schema(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", base.lower()).strip("_")
    if not base:
        base = "usuario"
    if base[0].isdigit():
        base = f"user_{base}"
    return base[:63]


def verificar_autorizacao(telefone: str) -> bool:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT autorizado FROM usuarios WHERE telefone = %s", (telefone,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado is not None and resultado[0] is True


def liberar_usuario(nome, telefone):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    schema = _normalizar_schema(nome)
    cursor.execute("""
        INSERT INTO usuarios (nome, telefone, schema_user, autorizado)
        VALUES (%s, %s, %s, true)
        ON CONFLICT (telefone) DO UPDATE SET autorizado = true, nome = EXCLUDED.nome, schema_user = EXCLUDED.schema_user
    """, (nome, telefone, schema))
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.gastos (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcelas INT DEFAULT 1,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.fatura_cartao (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcela TEXT,
            data_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_fim DATE
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.lembretes (
            id SERIAL PRIMARY KEY,
            telefone TEXT,
            mensagem TEXT,
            cron TEXT
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.salario (
            id SERIAL PRIMARY KEY,
            valor REAL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.email (
            id SERIAL PRIMARY KEY,
            telefone TEXT NOT NULL,
            email_user TEXT NOT NULL,
            email_pass TEXT NOT NULL,
            descricao TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
