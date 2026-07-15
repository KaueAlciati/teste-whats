import os
import requests
from dotenv import load_dotenv

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")  # fallback opcional

BASE_URL = "https://api.stlouisfed.org/fred"

def buscar_serie_fred(serie_id: str):
    """
    Consulta uma série do FRED (ex: SELIC, inflação, taxa de juros dos EUA, etc.)
    """
    url = f"{BASE_URL}/series/observations"
    params = {
        "series_id": serie_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }

    resposta = requests.get(url, params=params)
    if resposta.status_code == 200:
        dados = resposta.json()
        if dados["observations"]:
            ultima = dados["observations"][0]
            return {
                "data": ultima["date"],
                "valor": float(ultima["value"])
            }
        return {"erro": "Nenhum valor encontrado para a série."}
    else:
        return {"erro": f"Erro {resposta.status_code}: {resposta.text}"}

# Teste local
if __name__ == "__main__":
    # Exemplo: taxa de juros dos EUA (Federal Funds Rate)
    resultado = buscar_serie_fred("FEDFUNDS")
    print("📊 Último valor da série FEDFUNDS (Taxa de Juros dos EUA):")
    print(resultado)