# backend/investment_helper/sugestao_investimentos.py

from typing import Dict, List

def gerar_sugestao_investimentos(perfil: str, valor_total: float = 1000.0) -> Dict[str, float]:
    """
    Gera uma alocação de investimentos com base no perfil do usuário.
    Retorna um dicionário {classe_de_ativo: percentual}.

    Exemplo de uso:
    alocacao = gerar_sugestao_investimentos('Moderado', 2000)
    => {'Renda Fixa': 40, 'FIIs variados': 30, 'Ações Blue Chips': 20, 'Cripto': 10}
    """

    # Alocações básicas para cada perfil (em %)
    alocacao_perfis = {
        "Conservador": {
            "Renda Fixa (CDB/Tesouro)": 70,
            "FIIs defensivos": 20,
            "Ações": 10
        },
        "Moderado": {
            "Renda Fixa": 40,
            "FIIs variados": 30,
            "Ações Bluechips": 20,
            "Cripto": 10
        },
        "Arrojado": {
            "Renda Fixa": 20,
            "FIIs logísticos / shoppings": 30,
            "Ações de crescimento": 30,
            "Cripto": 20
        }
    }

    # Se perfil vier como "Conservador tendendo a Moderado" ou algo assim, pega a primeira palavra
    # Caso contrário, assume que a chave é exata
    perfil_base = perfil.split()[0].capitalize()
    if perfil_base not in alocacao_perfis:
        perfil_base = "Moderado"  # fallback se der algo diferente

    alocacao = alocacao_perfis[perfil_base]

    # Exemplo: se valor_total = 2000, e FIIs defensivos = 20%, user investe R$ 400 neles
    # Aqui apenas retornamos o dicionário de percentuais
    return alocacao


def montar_recomendacao_texto(perfil: str, valor_total: float) -> str:
    """
    Monta uma string amigável com recomendações,
    usando a alocação gerada e possivelmente exemplos concretos de ativos.
    """

    alocacao = gerar_sugestao_investimentos(perfil, valor_total)
    texto = [f"🧠 Seu perfil: {perfil}\n", f"💰 Montante total a investir: R$ {valor_total:,.2f}\n"]

    texto.append("🤖 Sugestão de alocação:\n")

    for classe, percentual in alocacao.items():
        valor_classe = (percentual / 100) * valor_total
        texto.append(f"• {classe}: {percentual}% (R$ {valor_classe:,.2f})\n")

    # Opcional: Integrar com suas APIs para pegar alguns exemplos de ativos
    # ex: top FIIs defensivos, etc.

    # Exemplo fictício de citar FII com maior DY
    if perfil.lower().startswith("arrojado"):
        texto.append("\n🔥 Exemplo: comprar Cripto via Exchange X, e Ações de Crescimento como TSLA, NVDA...\n")
    elif perfil.lower().startswith("conservador"):
        texto.append("\n🛡 Exemplo: aplicar maior parte em Tesouro Selic ou CDBs de bancos grandes.\n")
    else:
        texto.append("\n🏠 Exemplo: FIIs de logística, Ações Bluechips como ITUB4, PETR4...\n")

    return "".join(texto)


# Teste local
if __name__ == "__main__":
    perfil_user = "Moderado"
    valor_investir = 2000.0

    texto_final = montar_recomendacao_texto(perfil_user, valor_investir)
    print(texto_final)