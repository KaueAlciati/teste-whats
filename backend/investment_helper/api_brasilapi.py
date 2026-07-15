# backend/investment_helper/api_brasilapi.py
import requests
import datetime

def buscar_indicadores_brasilapi():
    url = "https://brasilapi.com.br/api/taxas/v1"
    resposta = requests.get(url)

    if resposta.status_code == 200:
        dados = resposta.json()

        # Vamos buscar Selic, CDI e IPCA
        indicadores_desejados = ["selic", "cdi", "ipca"]
        resultado = {}

        for item in dados:
            nome = item.get("nome")
            if nome and nome.lower() in indicadores_desejados:
                resultado[nome.upper()] = item.get("valor")

        return resultado
    else:
        return {"erro": f"Erro ao buscar dados: {resposta.status_code}"}

def buscar_feriados_nacionais(ano: int):
    url = f"https://brasilapi.com.br/api/feriados/v1/{ano}"
    resposta = requests.get(url)

    if resposta.status_code == 200:
        return resposta.json()
    else:
        return {"erro": f"Erro ao buscar feriados: {resposta.status_code}"}

# Teste local
if __name__ == "__main__":
    resultado = buscar_indicadores_brasilapi()
    print("📊 Indicadores BrasilAPI:")
    for nome, valor in resultado.items():
        print(f"{nome}: {valor}%")
    ano_atual = datetime.datetime.now().year
    feriados = buscar_feriados_nacionais(ano_atual)
    print(f"📅 Feriados nacionais de {ano_atual}:")
    if isinstance(feriados, list):
        for feriado in feriados:
            print(f"{feriado['date']} - {feriado['name']}")
    else:
        print(feriados)