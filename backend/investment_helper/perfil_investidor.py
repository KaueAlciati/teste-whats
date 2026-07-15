# backend/investment_helper/perfil_investidor.py

from typing import Dict, List

# Cada pergunta tem alternativas com pesos para "Conservador", "Moderado", "Arrojado"
PERGUNTAS = [
    {
        "pergunta": "Qual é o seu principal objetivo com os investimentos?",
        "pesos": [
            {"resposta": "Segurança / não perder dinheiro", "perfil": "Conservador", "peso": 2},
            {"resposta": "Renda passiva", "perfil": "Moderado", "peso": 1},
            {"resposta": "Aposentadoria no longo prazo", "perfil": "Moderado", "peso": 2},
            {"resposta": "Aumentar patrimônio agressivamente", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Em quanto tempo você pretende usar o dinheiro investido?",
        "pesos": [
            {"resposta": "Menos de 1 ano", "perfil": "Conservador", "peso": 2},
            {"resposta": "1 a 3 anos", "perfil": "Moderado", "peso": 1},
            {"resposta": "3 a 5 anos", "perfil": "Moderado", "peso": 2},
            {"resposta": "Acima de 5 anos", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Qual a sua principal fonte de renda?",
        "pesos": [
            {"resposta": "Salário fixo", "perfil": "Conservador", "peso": 1},
            {"resposta": "Variável (comissão, freelance)", "perfil": "Moderado", "peso": 1},
            {"resposta": "Renda passiva (aluguéis, dividendos, etc.)", "perfil": "Arrojado", "peso": 1},
        ]
    },
    {
        "pergunta": "Você possui uma reserva de emergência?",
        "pesos": [
            {"resposta": "Sim, de 3 a 6 meses de despesas", "perfil": "Moderado", "peso": 1},
            {"resposta": "Sim, mais de 6 meses", "perfil": "Conservador", "peso": 2},
            {"resposta": "Não", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Quanto da sua renda você consegue investir por mês?",
        "pesos": [
            {"resposta": "Até 10%", "perfil": "Conservador", "peso": 1},
            {"resposta": "Entre 10% e 30%", "perfil": "Moderado", "peso": 2},
            {"resposta": "Mais de 30%", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Como você reage quando vê seus investimentos caindo 10%?",
        "pesos": [
            {"resposta": "Vendo tudo!", "perfil": "Conservador", "peso": 2},
            {"resposta": "Fico preocupado, mas seguro", "perfil": "Moderado", "peso": 1},
            {"resposta": "Aproveito pra comprar mais", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Qual dessas frases mais representa você?",
        "pesos": [
            {"resposta": "Prefiro ganhar pouco, mas com segurança", "perfil": "Conservador", "peso": 2},
            {"resposta": "Estou disposto a correr algum risco pra ganhar mais", "perfil": "Moderado", "peso": 1},
            {"resposta": "Quanto maior o risco, maior a emoção (e o retorno!)", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Você já investe atualmente? Se sim, onde?",
        "pesos": [
            {"resposta": "Poupança", "perfil": "Conservador", "peso": 2},
            {"resposta": "Tesouro Direto / CDBs", "perfil": "Moderado", "peso": 1},
            {"resposta": "Ações / Criptomoedas / FIIs", "perfil": "Arrojado", "peso": 2},
            {"resposta": "Não invisto ainda", "perfil": "Conservador", "peso": 1},
        ]
    },
    {
        "pergunta": "Como você avalia seu conhecimento sobre investimentos?",
        "pesos": [
            {"resposta": "Nenhum / iniciante", "perfil": "Conservador", "peso": 2},
            {"resposta": "Intermediário", "perfil": "Moderado", "peso": 1},
            {"resposta": "Avançado", "perfil": "Arrojado", "peso": 2},
        ]
    },
    {
        "pergunta": "Você já ouviu falar em (Renda Fixa, Renda Variável, Diversificação, ETFs, FIIs)?",
        "pesos": [
            {"resposta": "Nunca ouvi falar em nada disso", "perfil": "Conservador", "peso": 2},
            {"resposta": "Conheço superficialmente alguns temas", "perfil": "Moderado", "peso": 1},
            {"resposta": "Sim, conheço bem todos", "perfil": "Arrojado", "peso": 2},
        ]
    },
]

def classificar_perfil(respostas: List[str]):
    """
    Recebe uma lista de respostas na mesma ordem de PERGUNTAS.
    Retorna:
      - perfil_final (str): 'Conservador', 'Moderado' ou 'Arrojado'
      - top3_respostas (List[dict]): as 3 respostas que mais pontuaram para o perfil
    """

    # Soma de pontos por perfil
    contagem = {"Conservador": 0, "Moderado": 0, "Arrojado": 0}

    # Guardar contribuições individuais
    # Ex: {"pergunta": "...", "resposta": "...", "perfil": "Arrojado", "peso": 2}
    contribuicoes = []

    for i, resposta in enumerate(respostas):
        if i >= len(PERGUNTAS):
            break

        pergunta_data = PERGUNTAS[i]
        resposta_lower = resposta.strip().lower()

        for opcao in pergunta_data["pesos"]:
            if opcao["resposta"].lower() == resposta_lower:
                peso = opcao.get("peso", 1)
                perfil_apontado = opcao["perfil"]
                contagem[perfil_apontado] += peso

                # Armazena a contribuição
                contribuicoes.append({
                    "pergunta": pergunta_data["pergunta"],
                    "resposta": opcao["resposta"],
                    "perfil": perfil_apontado,
                    "peso": peso
                })
                break

    # Ordena perfis por pontuação
    lista_perfis = sorted(contagem.items(), key=lambda x: x[1], reverse=True)
    perfil_mais, valor_mais = lista_perfis[0]
    perfil_segundo, valor_segundo = lista_perfis[1]

    # Lógica de empate/tendência
    if valor_mais == valor_segundo:
        perfil_final = f"Empate entre {perfil_mais} e {perfil_segundo}!"
    elif (valor_mais - valor_segundo) == 1:
        perfil_final = f"{perfil_mais} tendendo a {perfil_segundo}"
    else:
        perfil_final = perfil_mais

    # Filtra as contribuições que foram para o perfil_final (caso não seja 'Empate...')
    top3_respostas = []
    if "Empate" not in perfil_final and "tendendo" not in perfil_final:
        # Pega só as contribuições do perfil_final
        contrib_do_perfil = [c for c in contribuicoes if c["perfil"] == perfil_final]
        # Ordena por peso desc
        contrib_do_perfil.sort(key=lambda x: x["peso"], reverse=True)
        # Pega top 3
        top3_respostas = contrib_do_perfil[:3]

    return perfil_final, top3_respostas


# Teste local
if __name__ == "__main__":
    respostas_usuario = [
        "Aposentadoria no longo prazo",
        "3 a 5 anos",
        "Renda passiva (aluguéis, dividendos, etc.)",  # não existe 100% nas opcoes, mas ok
        "Não",
        "Entre 10% e 30%",
        "Aproveito pra comprar mais",
        "Quanto maior o risco, maior a emoção (e o retorno!)",
        "Ações / Criptomoedas / FIIs",
        "Intermediário",
        "Sim, conheço bem todos"
    ]

    perfil, top3 = classificar_perfil(respostas_usuario)
    print(f"🧠 Perfil do investidor: {perfil}\n")

    if top3:
        print("⭐ As 3 respostas que mais pesaram para esse perfil foram:")
        for contrib in top3:
            print(f"- [{contrib['peso']} pts] {contrib['pergunta']} => '{contrib['resposta']}'")