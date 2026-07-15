# backend/investment_helper/api_openfigi.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

OPENFIGI_API_KEY = os.getenv("OPENFIGI_API_KEY")

HEADERS = {
    "Content-Type": "application/json",
    "X-OPENFIGI-APIKEY": OPENFIGI_API_KEY
}

def buscar_info_figi(ticker: str):
    url = "https://api.openfigi.com/v3/mapping"
    payload = [
        {
            "idType": "TICKER",
            "idValue": ticker,
            "exchCode": "US"  # Pode adaptar para outras bolsas (ex: BR para Brasil)
        }
    ]

    resposta = requests.post(url, json=payload, headers=HEADERS)

    if resposta.status_code == 200:
        dados = resposta.json()
        if dados and dados[0].get("data"):
            ativo = dados[0]["data"][0]
            return {
                "ticker": ativo.get("ticker"),
                "name": ativo.get("name"),
                "figi": ativo.get("figi"),
                "exchCode": ativo.get("exchCode"),
                "marketSector": ativo.get("marketSector"),
                "securityType": ativo.get("securityType"),
                "shareClassFIGI": ativo.get("shareClassFIGI"),
                "compositeFIGI": ativo.get("compositeFIGI")
            }
        else:
            return {"erro": "Nenhum dado encontrado para esse ticker."}

    return {"erro": f"Erro {resposta.status_code}: {resposta.text}"}


# Teste local
if __name__ == "__main__":
    resultado = buscar_info_figi("AAPL")
    print("🔍 Informações do ativo via OpenFIGI:")
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")