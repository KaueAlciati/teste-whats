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
            channel_user_id TEXT,
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
            name TEXT,
            telefone TEXT UNIQUE,
            phone TEXT,
            schema_user TEXT,
            email TEXT,
            senha_hash TEXT,
            password_hash TEXT,
            senha_salt TEXT,
            is_active BOOLEAN DEFAULT true,
            email_verified BOOLEAN DEFAULT false,
            phone_verified BOOLEAN DEFAULT false,
            web_active BOOLEAN DEFAULT true,
            web_role TEXT DEFAULT 'user',
            web_last_login TIMESTAMP,
            last_login_at TIMESTAMP,
            web_avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            autorizado BOOLEAN DEFAULT false,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS name TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS phone TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS senha_hash TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_hash TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS senha_salt TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT false")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS web_active BOOLEAN DEFAULT true")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS web_role TEXT DEFAULT 'user'")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS web_last_login TIMESTAMP")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS web_avatar_url TEXT")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_auth_sessions (
            session_id UUID PRIMARY KEY,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            refresh_jti TEXT NOT NULL UNIQUE,
            refresh_expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            user_agent TEXT,
            ip_address TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_auth_sessions_usuario_id
        ON web_auth_sessions (usuario_id)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_channels (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            channel_user_id TEXT,
            phone_number TEXT,
            username TEXT,
            display_name TEXT,
            is_verified BOOLEAN NOT NULL DEFAULT false,
            verification_code_hash TEXT,
            verification_expires_at TIMESTAMP,
            linked_at TIMESTAMP,
            last_seen_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_channels_user_channel
        ON user_channels (user_id, channel)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_channels_channel_user
        ON user_channels (channel, channel_user_id)
        WHERE channel_user_id IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_channels_verification_hash
        ON user_channels (verification_code_hash)
        WHERE verification_code_hash IS NOT NULL
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_email_verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            verified_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS schema_user TEXT")
    cursor.execute("ALTER TABLE mensagens_recebidas ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'texto'")
    cursor.execute("ALTER TABLE mensagens_recebidas ADD COLUMN IF NOT EXISTS data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS channel_user_id TEXT")
    cursor.execute("UPDATE usuarios SET name = COALESCE(name, nome)")
    cursor.execute("UPDATE usuarios SET nome = COALESCE(nome, name)")
    cursor.execute("UPDATE usuarios SET phone = COALESCE(phone, telefone)")
    cursor.execute("UPDATE usuarios SET telefone = COALESCE(telefone, phone)")
    cursor.execute("UPDATE usuarios SET password_hash = COALESCE(password_hash, senha_hash)")
    cursor.execute("UPDATE usuarios SET senha_hash = COALESCE(senha_hash, password_hash)")
    cursor.execute("UPDATE usuarios SET is_active = COALESCE(is_active, web_active, autorizado, true)")
    cursor.execute("UPDATE usuarios SET web_active = COALESCE(web_active, is_active, true)")
    cursor.execute("UPDATE usuarios SET email_verified = COALESCE(email_verified, false)")
    cursor.execute("UPDATE usuarios SET phone_verified = COALESCE(phone_verified, false)")
    cursor.execute("UPDATE usuarios SET created_at = COALESCE(created_at, data_inclusao, NOW())")
    cursor.execute("UPDATE usuarios SET updated_at = COALESCE(updated_at, created_at, NOW())")
    cursor.execute("UPDATE usuarios SET last_login_at = COALESCE(last_login_at, web_last_login)")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_unique
        ON usuarios (LOWER(email))
        WHERE email IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_phone_unique
        ON usuarios (phone)
        WHERE phone IS NOT NULL
    """)
    conn.commit()
    cursor.close()
    conn.close()
