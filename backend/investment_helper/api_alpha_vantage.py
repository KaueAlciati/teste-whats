import os
import requests
from dotenv import load_dotenv
load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

def buscar_acao_alpha_vantage(simbolo: str):
    url = f"https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": simbolo,
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    resposta = requests.get(url, params=params)
    if resposta.status_code == 200:
        dados = resposta.json().get("Global Quote", {})
        if dados:
            return {
                "atual": float(dados.get("05. price", 0)),
                "alta": float(dados.get("03. high", 0)),
                "baixa": float(dados.get("04. low", 0)),
                "abertura": float(dados.get("02. open", 0)),
                "anterior": float(dados.get("08. previous close", 0)),
                "volume": int(dados.get("06. volume", 0))
            }
    return {"erro": "Falha ao buscar dados da Alpha Vantage"}

# Exemplo de teste
if __name__ == "__main__":
    simbolo = "AAPL"
    resultado = buscar_acao_alpha_vantage(simbolo)
    print("📊 Resultado da API Alpha Vantage:")
    print(resultado)