# backend/investment_helper/api_twelve_data.py
import os
import requests
from dotenv import load_dotenv
load_dotenv()

TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

def buscar_acao_twelve_data(simbolo: str):
    url = f"https://api.twelvedata.com/quote?symbol={simbolo}&apikey={TWELVE_API_KEY}"
    resposta = requests.get(url)

    if resposta.status_code == 200:
        dados = resposta.json()
        if "close" not in dados:
            print("🔎 Resposta completa da API:")
            print(dados)
            return {"erro": dados.get("message", "Erro desconhecido")}

        return {
            "nome": dados.get("name"),
            "simbolo": dados.get("symbol"),
            "atual": float(dados.get("close")),  # <- aqui
            "alta": float(dados.get("high")),
            "baixa": float(dados.get("low")),
            "abertura": float(dados.get("open")),
            "anterior": float(dados.get("previous_close")),
            "volume": int(dados.get("volume"))
        }

    return {"erro": "Falha ao buscar dados da Twelve Data"}

# Teste local
if __name__ == "__main__":
    simbolo = "AAPL"
    resultado = buscar_acao_twelve_data(simbolo)

    print("📊 Resultado da API Twelve Data:")
    for chave, valor in resultado.items():
        print(f"{chave.capitalize()}: {valor}")