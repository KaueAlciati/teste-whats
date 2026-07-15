# backend/investment_helper/api_coingecko.py
import requests

def buscar_top_criptos(limit=5):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "percent_change_24h_desc",
        "per_page": limit,
        "page": 1,
        "price_change_percentage": "1h,24h,7d"
    }

    resposta = requests.get(url, params=params)
    if resposta.status_code == 200:
        criptos = resposta.json()
        return [
            {
                "nome": cripto["name"],
                "simbolo": cripto["symbol"].upper(),
                "preco_usd": cripto["current_price"],
                "variacao_24h": cripto["price_change_percentage_24h"],
                "market_cap": cripto["market_cap"],
                "ranking": cripto["market_cap_rank"]
            }
            for cripto in criptos
        ]
    return {"erro": "Erro ao buscar dados de criptomoedas"}

if __name__ == "__main__":
    criptos = buscar_top_criptos()
    print("🔥 Top criptos em alta nas últimas 24h:")
    for c in criptos:
        print(f"{c['ranking']}º {c['nome']} ({c['simbolo']}): ${c['preco_usd']} | 24h: {c['variacao_24h']:.2f}%")