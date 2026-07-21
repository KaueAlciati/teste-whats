from __future__ import annotations

import logging
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")


def conectar_bd():
    return psycopg2.connect(DATABASE_URL)


def inicializar_bd(database_url: str | None = None):
    url = database_url or DATABASE_URL
    if not url:
        logger.warning("DATABASE_URL ausente; banco não inicializado.")
        return

    conn = psycopg2.connect(url)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcelas INT DEFAULT 1,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salario (
            id SERIAL PRIMARY KEY,
            valor REAL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receitas (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL NOT NULL,
            origem TEXT,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fatura_cartao (
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lembretes (
            id SERIAL PRIMARY KEY,
            telefone TEXT,
            mensagem TEXT,
            cron TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensagens_recebidas (
            id SERIAL PRIMARY KEY,
            mensagem_id TEXT UNIQUE,
            telefone TEXT,
            tipo TEXT DEFAULT 'texto',
            data_recebida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('user', 'assistant')),
            message_type TEXT NOT NULL DEFAULT 'text',
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_user_channel_created_at
        ON conversation_messages (user_id, channel, created_at DESC)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            telefone TEXT UNIQUE,
            schema_user TEXT,
            autorizado BOOLEAN DEFAULT false,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens_ativos (
            id SERIAL PRIMARY KEY,
            telefone TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            schema TEXT NOT NULL,
            criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
            expira_em TIMESTAMP NOT NULL
        )
    """)
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS schema_user TEXT")
    cursor.execute("ALTER TABLE mensagens_recebidas ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'texto'")
    cursor.execute("ALTER TABLE mensagens_recebidas ADD COLUMN IF NOT EXISTS data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    conn.commit()
    cursor.close()
    conn.close()
