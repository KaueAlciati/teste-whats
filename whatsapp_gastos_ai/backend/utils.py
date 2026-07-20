from __future__ import annotations

import os
from datetime import datetime

import psycopg2
import pytz

from backend.services.db_init import conectar_bd

DATABASE_URL = os.getenv("DATABASE_URL")
fuso_brasilia = pytz.timezone("America/Sao_Paulo")


def obter_schema_por_telefone(telefone):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT schema_user FROM usuarios WHERE telefone = %s AND autorizado = true", (telefone,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado[0] if resultado and resultado[0] else None


def mensagem_ja_processada(mensagem_id: str) -> bool:
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM mensagens_recebidas WHERE mensagem_id = %s", (mensagem_id,))
    existe = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return existe


def registrar_mensagem_recebida(mensagem_id: str, telefone: str = "", tipo: str = "texto"):
    agora = datetime.now(fuso_brasilia)
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mensagens_recebidas (mensagem_id, telefone, tipo, data_recebida, data_processamento)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (mensagem_id, telefone, tipo, agora, agora))
    conn.commit()
    cursor.close()
    conn.close()


def salvar_localizacao_usuario(telefone, latitude, longitude):
    conn = conectar_bd()
    cursor = conn.cursor()
    schema = obter_schema_por_telefone(telefone)
    if not schema:
        cursor.close()
        conn.close()
        return
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.localizacoes_usuario (
            id SERIAL PRIMARY KEY,
            telefone TEXT,
            latitude FLOAT,
            longitude FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(f"""
        INSERT INTO {schema}.localizacoes_usuario (telefone, latitude, longitude)
        VALUES (%s, %s, %s)
    """, (telefone, latitude, longitude))
    conn.commit()
    cursor.close()
    conn.close()


def obter_ultima_localizacao(telefone):
    conn = conectar_bd()
    cursor = conn.cursor()
    schema = obter_schema_por_telefone(telefone)
    if not schema:
        cursor.close()
        conn.close()
        return None
    cursor.execute(f"""
        SELECT latitude, longitude, timestamp FROM {schema}.localizacoes_usuario
        WHERE telefone = %s
        ORDER BY timestamp DESC
        LIMIT 1
    """, (telefone,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    if resultado:
        return {"latitude": resultado[0], "longitude": resultado[1], "timestamp": resultado[2]}
    return None
