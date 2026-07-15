# backend/investment_helper/api_finnhub.py
import os
import requests
from dotenv import load_dotenv
load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

def buscar_acao_finnhub(simbolo: str):
    url = f"https://finnhub.io/api/v1/quote?symbol={simbolo}&token={FINNHUB_API_KEY}"
    resposta = requests.get(url)
    if resposta.status_code == 200:
        dados = resposta.json()
        return {
            "atual": dados.get("c"),
            "alta": dados.get("h"),
            "baixa": dados.get("l"),
            "abertura": dados.get("o"),
            "anterior": dados.get("pc")
        }
    return {"erro": "Falha ao buscar dados"}

simbolo = "AAPL"
resultado = buscar_acao_finnhub(simbolo)

print("📈 Resultado da API Finnhub:")
print(resultado)