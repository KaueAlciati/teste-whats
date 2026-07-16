import logging
import os
import psycopg2
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")


def conectar_bd():
    return psycopg2.connect(DATABASE_URL)


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_exists(cursor, schema: str, table: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        )
        """,
        (schema, table),
    )
    return cursor.fetchone()[0]


def _column_exists(cursor, schema: str, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
        )
        """,
        (schema, table, column),
    )
    return cursor.fetchone()[0]


def _add_column_if_missing(cursor, schema: str, table: str, column: str, definition: str) -> bool:
    if _column_exists(cursor, schema, table, column):
        logger.info(f"✅ Coluna {schema}.{table}.{column} já existe.")
        return False

    logger.info(f"🛠️ Criando coluna {schema}.{table}.{column}...")
    cursor.execute(
        f'ALTER TABLE {_quote_ident(schema)}.{_quote_ident(table)} ADD COLUMN {_quote_ident(column)} {definition}'
    )
    logger.info(f"✅ Coluna {schema}.{table}.{column} criada com sucesso.")
    return True


def _migrar_tabela_mensagens_recebidas(cursor):
    logger.info("📦 Verificando tabela mensagens_recebidas...")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS public.mensagens_recebidas (
            id SERIAL PRIMARY KEY,
            mensagem_id TEXT UNIQUE,
            telefone TEXT,
            data_recebida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    _add_column_if_missing(cursor, "public", "mensagens_recebidas", "tipo", "TEXT")
    _add_column_if_missing(cursor, "public", "mensagens_recebidas", "data_processamento", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if _column_exists(cursor, "public", "mensagens_recebidas", "data_recebida") and _column_exists(cursor, "public", "mensagens_recebidas", "data_processamento"):
        cursor.execute(
            """
            UPDATE public.mensagens_recebidas
            SET data_processamento = COALESCE(data_processamento, data_recebida)
            WHERE data_processamento IS NULL AND data_recebida IS NOT NULL
            """
        )

    if _column_exists(cursor, "public", "mensagens_recebidas", "tipo"):
        cursor.execute(
            """
            UPDATE public.mensagens_recebidas
            SET tipo = COALESCE(tipo, 'texto')
            WHERE tipo IS NULL
            """
        )


def _migrar_tabela_usuarios(cursor):
    logger.info("📦 Verificando tabela usuarios...")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS public.usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            telefone TEXT UNIQUE,
            autorizado BOOLEAN DEFAULT false,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    _add_column_if_missing(cursor, "public", "usuarios", "schema_user", "TEXT")


def _migrar_tabela_gastos(cursor, schema: str = "public"):
    logger.info(f"📦 Verificando tabela gastos ({schema})...")

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_quote_ident(schema)}.{_quote_ident('gastos')} (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcelas INT DEFAULT 1,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    _add_column_if_missing(cursor, schema, "gastos", "tipo", "TEXT")


def _migrar_schemas_usuarios(cursor):
    logger.info("📦 Verificando schemas dos usuários...")

    cursor.execute(
        """
        SELECT DISTINCT schema_user
        FROM public.usuarios
        WHERE schema_user IS NOT NULL
          AND TRIM(schema_user) <> ''
        """
    )

    for (schema_name,) in cursor.fetchall():
        logger.info(f"📂 Verificando schema: {schema_name}")
        schema_ident = _quote_ident(schema_name)
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_ident}")
        _migrar_tabela_gastos(cursor, schema_name)


def inicializar_bd(DATABASE_URL):
    logger.info("==============================================")
    logger.info("🚀 INICIANDO MIGRAÇÃO DO BANCO")
    logger.info("==============================================")

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcelas INT DEFAULT 1,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS salario (
            id SERIAL PRIMARY KEY,
            valor REAL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
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
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lembretes (
            id SERIAL PRIMARY KEY,
            telefone TEXT,
            mensagem TEXT,
            cron TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens_ativos (
            id SERIAL PRIMARY KEY,
            telefone TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            schema TEXT NOT NULL,
            criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
            expira_em TIMESTAMP NOT NULL
        )
        """
    )

    _migrar_tabela_mensagens_recebidas(cursor)
    _migrar_tabela_usuarios(cursor)
    _migrar_tabela_gastos(cursor, "public")
    _migrar_schemas_usuarios(cursor)

    conn.commit()

    logger.info("==============================================")
    logger.info("✅ MIGRAÇÃO FINALIZADA COM SUCESSO")
    logger.info("==============================================")

    cursor.close()
    conn.close()