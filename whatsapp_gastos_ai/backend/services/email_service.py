from __future__ import annotations

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def obter_schema_por_telefone(telefone):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT schema_user FROM usuarios WHERE telefone = %s AND autorizado = true", (telefone,))
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return resultado[0] if resultado and resultado[0] else None


def salvar_credenciais_email(telefone, email_user, email_pass, descricao=None):
    schema = obter_schema_por_telefone(telefone)
    if not schema:
        return


def listar_emails_cadastrados(telefone):
    return []


def buscar_credenciais_email(telefone, email_especifico=None):
    return None, None


def formatar_emails_para_whatsapp(emails_info):
    return "📧 Nenhum e-mail disponível."


def get_emails_info(email_user, email_pass, data_consulta=None):
    return []
