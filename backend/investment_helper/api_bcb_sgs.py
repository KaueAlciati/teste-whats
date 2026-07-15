# backend/investment_helper/api_bcb_sgs.py
import requests
from datetime import datetime, timedelta

def buscar_indicadores_bcb():
    indicadores = {
        "SELIC": 4189,         # Meta Selic
        "IPCA": 433,           # IPCA
        "IGPM": 189,           # IGP-M
        "PIB": 7326,           # PIB Trimestral (variação %)
        "USD/BRL": 1           # Dólar comercial (compra)
    }

    hoje = datetime.today()
    inicio = hoje - timedelta(days=90)

    data_inicio = inicio.strftime("%d/%m/%Y")
    data_fim = hoje.strftime("%d/%m/%Y")

    resultados = {}

    for nome, codigo in indicadores.items():
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
            f"?formato=json&dataInicial={data_inicio}&dataFinal={data_fim}"
        )
        resposta = requests.get(url)
        if resposta.status_code == 200:
            dados = resposta.json()
            if dados:
                ultimo = dados[-1]
                resultados[nome] = {
                    "data": ultimo["data"],
                    "valor": float(ultimo["valor"].replace(",", "."))
                }
            else:
                resultados[nome] = {"erro": "Sem dados recentes"}
        else:
            resultados[nome] = {"erro": f"Erro {resposta.status_code}"}

    return resultados

# Teste local
if __name__ == "__main__":
    resultado = buscar_indicadores_bcb()
    print("📊 Indicadores via Banco Central (SGS):")
    for nome, info in resultado.items():
        if "erro" in info:
            print(f"{nome}: {info['erro']}")
        else:
            print(f"{nome}: {info['valor']} (em {info['data']})")