# backend/investment_helper/api_b3_yfinance.py

import yfinance as yf

def buscar_acao_b3(simbolo_b3: str):
    """
    Retorna informações básicas de uma ação da B3 usando yfinance.
    Ex: 'PETR4.SA', 'ITUB4.SA'
    """
    try:
        acao = yf.Ticker(simbolo_b3)
        info = acao.info

        return {
            "nome": info.get("longName"),
            "simbolo": info.get("symbol"),
            "preco_atual": info.get("currentPrice"),
            "dia_alta": info.get("dayHigh"),
            "dia_baixa": info.get("dayLow"),
            "abertura": info.get("open"),
            "fechamento_anterior": info.get("previousClose"),
            "volume": info.get("volume"),
            "setor": info.get("sector"),
            "site_empresa": info.get("website")
        }

    except Exception as e:
        return {"erro": f"Erro ao buscar dados: {str(e)}"}

# Teste local
if __name__ == "__main__":
    simbolo = "PETR4.SA"
    resultado = buscar_acao_b3(simbolo)

    print("📊 Informações da ação da B3 via Yahoo Finance:")
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")