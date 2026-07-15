# backend/investment_helper/analisador.py

from backend.investment_helper.api_alpha_vantage import buscar_acao_alpha_vantage
from backend.investment_helper.api_finnhub import buscar_acao_finnhub
from backend.investment_helper.api_twelve_data import buscar_acao_twelve_data
from backend.investment_helper.api_coingecko import buscar_top_criptos
from backend.investment_helper.api_openfigi import buscar_info_figi
from backend.investment_helper.api_fred import buscar_serie_fred
from backend.investment_helper.api_brasilapi import buscar_indicadores_brasilapi
from backend.investment_helper.api_bcb_sgs import buscar_indicadores_bcb
from backend.investment_helper.api_b3_yfinance import buscar_acao_b3
from backend.investment_helper.api_fii_yfinance import buscar_fii_yfinance
from backend.investment_helper.api_fii_fundsexplorer import buscar_info_fii_funds_explorer


def resumo_acao(simbolo: str):
    print("\n📊 Resumo da ação:")

    print("\n🔷 Yahoo Finance:")
    print(buscar_acao_b3(simbolo))

    print("\n🔷 Finnhub:")
    print(buscar_acao_finnhub(simbolo))

    print("\n🔷 Twelve Data:")
    print(buscar_acao_twelve_data(simbolo))

    print("\n🔷 Alpha Vantage:")
    print(buscar_acao_alpha_vantage(simbolo))

    print("\n🔷 Setor (OpenFIGI):")
    print(buscar_info_figi(simbolo))


def resumo_fii(ticker: str):
    print("\n🏢 Resumo do FII:")

    print("\n🔷 Yahoo Finance:")
    print(buscar_fii_yfinance(ticker))

    print("\n🔷 FundsExplorer:")
    print(buscar_info_fii_funds_explorer(ticker))


def resumo_macro_brasil():
    print("\n🌎 Indicadores BrasilAPI:")
    print(buscar_indicadores_brasilapi())

    print("\n🌎 Indicadores Banco Central (SGS):")
    print(buscar_indicadores_bcb())


def resumo_macro_usa():
    print("\n🇺🇸 Indicadores EUA (FRED):")
    print("FED Funds Rate:", buscar_serie_fred("FEDFUNDS"))


def resumo_cripto():
    print("\n🔥 Criptomoedas em destaque:")
    for c in buscar_top_criptos():
        simbolo = c["simbolo"]
        nome = c["nome"]
        preco = c["preco_usd"]
        variacao = c["variacao_24h"]
        seta = "🔺" if variacao >= 0 else "🔻"
        print(f"{nome} ({simbolo}): ${preco} | 24h: {seta} {variacao:.2f}%")


if __name__ == "__main__":
    # Exemplos de chamadas
    resumo_acao("AAPL")
    resumo_fii("MXRF11")
    resumo_macro_brasil()
    resumo_macro_usa()
    resumo_cripto()
