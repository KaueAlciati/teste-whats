# backend/investment_helper/api_fii_yfinance.py
import yfinance as yf

def buscar_fii_yfinance(fii_codigo: str):
    """
    Busca informações básicas de um FII brasileiro usando Yahoo Finance.
    Ex: MXRF11, KNRI11, HGLG11
    """
    try:
        ticker = yf.Ticker(f"{fii_codigo.upper()}.SA")
        info = ticker.info

        return {
            "nome": info.get("longName"),
            "simbolo": info.get("symbol"),
            "preco_atual": info.get("regularMarketPrice"),
            "alta_dia": info.get("dayHigh"),
            "baixa_dia": info.get("dayLow"),
            "abertura": info.get("regularMarketOpen"),
            "fechamento_anterior": info.get("previousClose"),
            "volume": info.get("volume"),
            "setor": info.get("sector"),
            "site": info.get("website"),
        }

    except Exception as e:
        return {"erro": f"Erro ao buscar dados do FII: {str(e)}"}


# Teste local
if __name__ == "__main__":
    resultado = buscar_fii_yfinance("MXRF11")
    print("🏢 Informações do FII via Yahoo Finance:")
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")