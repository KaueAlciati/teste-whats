from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MOEDAS_FILE = DATA_DIR / "moedas.json"
CONVERSOES_FILE = DATA_DIR / "conversoes.json"

logger = logging.getLogger(__name__)

if not MOEDAS_FILE.exists():
    raise FileNotFoundError(f"Arquivo de moedas não encontrado: {MOEDAS_FILE}")

if not CONVERSOES_FILE.exists():
    raise FileNotFoundError(f"Arquivo de conversões não encontrado: {CONVERSOES_FILE}")

with MOEDAS_FILE.open("r", encoding="utf-8") as file:
    dados_moedas = json.load(file)
with CONVERSOES_FILE.open("r", encoding="utf-8") as file:
    dados_conversoes = json.load(file)

API_COTACAO = os.getenv("API_COTACAO")
API_CEP = os.getenv("API_CEP")
CONVERSOES = dados_conversoes.get("conversoes_disponiveis", {})
MOEDAS = dados_moedas.get("todas_moedas", {})
MOEDA_EMOJIS = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🏴", "BTC": "🪙", "ETH": "💎"}


def obter_cotacao_principais(API_COTACAO, MOEDA_EMOJIS):
    if not API_COTACAO:
        return "⚠️ API de cotação não configurada."
    moedas = ["USD", "EUR", "GBP", "BTC", "ETH"]
    url = f"{API_COTACAO}" + ",".join([f"{m}-BRL" for m in moedas])
    try:
        response = requests.get(url)
        data = response.json()
        cotacoes = []
        for moeda in moedas:
            key = f"{moeda}BRL"
            if key in data:
                valor = float(data[key]["bid"])
                emoji = MOEDA_EMOJIS.get(moeda, "💰")
                cotacoes.append(f"{emoji} {moeda}: R$ {valor:,.2f}")
        return "📈 Cotações principais:\n\n" + "\n".join(cotacoes)
    except Exception as exc:
        logger.exception("Erro ao buscar cotações.")
        return f"❌ Erro ao buscar cotações: {str(exc)}"


def obter_cotacao(API_COTACAO, MOEDAS, CONVERSOES, moeda_origem, moeda_destino="BRL"):
    if not API_COTACAO:
        return "⚠️ API de cotação não configurada."
    moeda_origem = moeda_origem.upper()
    moeda_destino = moeda_destino.upper()
    nome_origem = MOEDAS.get(moeda_origem, moeda_origem)
    nome_destino = MOEDAS.get(moeda_destino, moeda_destino)
    try:
        response = requests.get(f"{API_COTACAO}{moeda_origem}-{moeda_destino}")
        response.raise_for_status()
        data = response.json()
        key = f"{moeda_origem}{moeda_destino}"
        if key in data:
            valor = float(data[key]["bid"])
            return f"💱 Conversão: {nome_origem} → {nome_destino}\n💰 1 {moeda_origem} = {valor:.4f} {moeda_destino}"
        return "⚠️ Conversão não encontrada."
    except Exception as exc:
        logger.exception("Erro ao buscar cotação.")
        return f"❌ Erro ao buscar cotação: {str(exc)}"


def listar_moedas_disponiveis(MOEDAS):
    return "\n".join(["🪙 Moedas disponíveis:"] + [f"• {codigo}: {nome}" for codigo, nome in sorted(MOEDAS.items())])


def listar_conversoes_disponiveis(CONVERSOES):
    return "\n".join(["💱 Conversões disponíveis:"] + [f"• {origem} → {', '.join(sorted(destinos))}" for origem, destinos in sorted(CONVERSOES.items())])


def listar_conversoes_disponiveis_moeda(CONVERSOES, origem):
    moeda = origem.upper()
    destinos = sorted(CONVERSOES.get(moeda, []))
    if not destinos:
        return f"⚠️ Nenhuma conversão disponível para {moeda}."
    return "\n".join([f"💱 Conversões disponíveis pra {moeda}:", f"• {moeda} → {', '.join(destinos)}"])


def buscar_cep(cep: str):
    if not API_CEP:
        return "⚠️ API de CEP não configurada."
    try:
        response = requests.get(f"{API_CEP}{cep}")
        if response.status_code == 200:
            dados = response.json()
            return (
                f"📍 Endereço encontrado:\n"
                f"• CEP: {dados.get('cep')}\n"
                f"• Logradouro: {dados.get('address')}\n"
                f"• Bairro: {dados.get('district')}\n"
                f"• Cidade: {dados.get('city')} - {dados.get('state')}\n"
                f"• DDD: {dados.get('ddd')}"
            )
        if response.status_code == 400:
            return "❌ CEP inválido."
        if response.status_code == 404:
            return "🔍 CEP não encontrado."
        return f"⚠️ Erro inesperado (status {response.status_code})."
    except requests.RequestException as exc:
        return f"❌ Erro ao buscar o CEP: {str(exc)}"
