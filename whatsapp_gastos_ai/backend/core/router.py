from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.sessions import SessionData
from backend.services.api_service import (
    CONVERSOES,
    MOEDAS,
    MOEDA_EMOJIS,
    buscar_cep,
    listar_conversoes_disponiveis,
    listar_conversoes_disponiveis_moeda,
    listar_moedas_disponiveis,
    obter_cotacao,
    obter_cotacao_principais,
)
from backend.services.autorizacao_service import liberar_usuario, verificar_autorizacao
from backend.services.bot_grafica import gerar_resposta_bot as gerar_resposta_grafica
from backend.services.conversational_ai import gerar_resposta_conversacional
from backend.services.gastos_service import apagar_lembrete, calcular_total_gasto, listar_lembretes, pagar_fatura, registrar_salario, salvar_gasto
from backend.services.maps_service import calcular_rota
from backend.services.noticias_service import obter_boletim_the_news
from backend.services.scheduler import agendar_lembrete_cron
from backend.services.token_service import gerar_token_acesso
from backend.services.email_service import buscar_credenciais_email, formatar_emails_para_whatsapp, get_emails_info, listar_emails_cadastrados, salvar_credenciais_email
from backend.utils import obter_schema_por_telefone, salvar_localizacao_usuario

logger = logging.getLogger(__name__)


def _normalizar_texto(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", base.lower()).strip()


def _ajuda_texto(is_admin: bool = False) -> str:
    blocos = [
        "Posso ajudar com:",
        "",
        "💰 Financeiro",
        "• Registrar gastos",
        "• Consultar total gasto",
        "• Controlar faturas e salário",
        "• Ver gráficos",
        "",
        "⏰ Organização",
        "• Criar e consultar lembretes",
        "• Consultar e-mails",
        "",
        "🔎 Consultas",
        "• Cotação",
        "• CEP",
        "• Rotas",
        "• Notícias",
        "",
        "🎨 Gráfica",
        "• Orçamentos",
        "• Adesivos",
        "• Banners",
        "• Placas",
        "• Fachadas",
        "",
        "Você também pode simplesmente me explicar o que precisa.",
    ]
    if is_admin:
        blocos.extend(
            [
                "",
                "Administração",
                "• Liberar usuário",
                "• Revogar usuário",
            ]
        )
    return "\n".join(blocos)


def _extrair_valor(texto: str) -> float | None:
    match = re.search(r"(?:r\$|rs)?\s*(\d+(?:[.,]\d{1,2})?)", texto, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _identificar_modo_grafica(texto_normalizado: str) -> bool:
    palavras = {
        "grafica",
        "orcamento",
        "orcamentos",
        "adesivo",
        "banner",
        "placa",
        "fachada",
        "impressao",
        "comunicacao visual",
        "plotter",
        "cartao de visita",
        "flyer",
        "panfleto",
    }
    return any(palavra in texto_normalizado for palavra in palavras)


def _identificar_intencao_deterministica(texto: str, texto_normalizado: str) -> str | None:
    if texto_normalizado in {"ajuda", "menu", "comandos"}:
        return "ajuda"
    if texto_normalizado == "total gasto" or any(
        frase in texto_normalizado
        for frase in {
            "quanto eu gastei",
            "quanto gastei",
            "meu total gasto",
            "total de gastos",
            "total dos gastos",
        }
    ):
        return "total_gasto"
    if texto_normalizado == "fatura paga" or texto_normalizado == "fatura paga!":
        return "fatura_paga"
    if texto_normalizado == "gráficos" or texto_normalizado == "graficos":
        return "graficos"
    if texto_normalizado.startswith("cep ") or re.search(r"\b\d{8}\b", texto_normalizado):
        return "cep"
    if texto_normalizado == "cotação" or texto_normalizado == "cotacao":
        return "cotacao"
    if texto_normalizado.startswith("notícias") or texto_normalizado.startswith("noticias"):
        return "noticias"
    if texto_normalizado.startswith("emails") or texto_normalizado.startswith("e-mails") or texto_normalizado.startswith("email"):
        return "emails"
    if texto_normalizado == "rotas" or texto_normalizado.startswith("rota ") or texto_normalizado.startswith("rotas "):
        return "rotas"
    if texto_normalizado.startswith("lista lembretes") or texto_normalizado.startswith("apagar lembrete") or texto_normalizado.startswith("tabela cron"):
        return "lembretes"
    if texto_normalizado.startswith("salario ") or texto_normalizado.startswith("salário "):
        return "salario"
    if any(verbo in texto_normalizado for verbo in {"gastei", "paguei", "comprei", "paguei com", "gasto "}):
        if _extrair_valor(texto) is not None:
            return "registrar_gasto"
    return None


async def _responder_ajuda(telefone: str) -> AgentResponse:
    logger.info("Comando identificado: ajuda (%s)", telefone)
    return AgentResponse(text=_ajuda_texto(is_admin=telefone == os.getenv("ADMIN_PHONE")), metadata={"intent": "ajuda"})


async def _responder_total_gasto(telefone: str, session: SessionData) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
    if schema:
        session.state["schema"] = schema
    total = calcular_total_gasto(schema) if schema else 0.0
    logger.info("Comando identificado: total gasto (%s)", telefone)
    return AgentResponse(
        text=f"📊 Total gasto no mês: R$ {format(total, ',.2f').replace(',', '.')}",
        metadata={"intent": "total_gasto"},
    )


async def _responder_fatura_paga(telefone: str, session: SessionData) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
    if schema:
        session.state["schema"] = schema
        pagar_fatura(schema)
    logger.info("Comando identificado: fatura paga (%s)", telefone)
    return AgentResponse(text="✅ Fatura registrada como paga.", metadata={"intent": "fatura_paga"})


async def _responder_graficos(telefone: str, session: SessionData) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
    if schema:
        session.state["schema"] = schema
        token_info = gerar_token_acesso(telefone)
        token = token_info["token"]
        expira_em = token_info["expira_em"]
        logger.info("Comando identificado: gráficos (%s)", telefone)
        return AgentResponse(
            text=(
                "📊 Aqui está o seu link com os gráficos financeiros!\n\n"
                f"🔗 https://dashboard-financas.up.railway.app/?phone={telefone}&token={token}\n"
                f"⚠️ O link é válido até às {expira_em.strftime('%H:%M')} por segurança."
            ),
            metadata={"intent": "graficos", "token": token},
        )
    return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": "graficos"})


async def _responder_cep(texto: str) -> AgentResponse:
    partes = texto.split()
    if len(partes) == 2 and partes[1].isdigit():
        logger.info("Comando identificado: CEP")
        return AgentResponse(text=buscar_cep(partes[1]), metadata={"intent": "cep"})
    match = re.search(r"\b(\d{8})\b", texto)
    if match:
        logger.info("Intenção identificada: CEP")
        return AgentResponse(text=buscar_cep(match.group(1)), metadata={"intent": "cep"})
    return AgentResponse(text="❌ Formato inválido. Use: `cep 05424020` (apenas números).", metadata={"intent": "cep"})


async def _responder_cotacao(texto: str, texto_normalizado: str) -> AgentResponse:
    logger.info("Comando/intençao identificado: cotação")
    if texto_normalizado in {"cotação", "cotacao"}:
        return AgentResponse(text=obter_cotacao_principais(os.getenv("API_COTACAO"), MOEDA_EMOJIS), metadata={"intent": "cotacao"})

    partes = texto.split()
    if len(partes) == 2:
        moeda = partes[1].upper()
        return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, moeda), metadata={"intent": "cotacao"})

    if "-" in texto:
        moedas = re.split(r"[-/]", texto.split(maxsplit=1)[-1])
        if len(moedas) >= 2:
            origem = moedas[0].strip().upper()
            destino = moedas[1].strip().upper()
            return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, origem, destino), metadata={"intent": "cotacao"})

    mapa_moedas = {
        "dolar": "USD",
        "dolar americano": "USD",
        "euro": "EUR",
        "libra": "GBP",
        "iene": "JPY",
        "peso": "ARS",
    }
    for chave, moeda in mapa_moedas.items():
        if chave in texto_normalizado:
            return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, moeda), metadata={"intent": "cotacao"})
    return AgentResponse(text=obter_cotacao_principais(os.getenv("API_COTACAO"), MOEDA_EMOJIS), metadata={"intent": "cotacao"})


async def _responder_registrar_gasto(message: IncomingMessage, session: SessionData) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(message.user_id)
    if schema:
        session.state["schema"] = schema
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": "registrar_gasto"})

    valor = _extrair_valor(message.text or "")
    if valor is None:
        return AgentResponse(text="Quanto foi o gasto? Me manda o valor que eu registro.", metadata={"intent": "registrar_gasto"})

    texto = _normalizar_texto(message.text or "")
    descricao = (message.text or "").strip()
    categoria = "geral"
    if any(palavra in texto for palavra in {"almoco", "almoço", "jantar", "cafe", "lanche", "mercado", "supermercado"}):
        categoria = "alimentacao"
    elif any(palavra in texto for palavra in {"uber", "taxi", "transporte", "combustivel", "gasolina"}):
        categoria = "transporte"
    elif any(palavra in texto for palavra in {"internet", "celular", "assinatura", "streaming"}):
        categoria = "servicos"

    meio_pagamento = "não informado"
    if "pix" in texto:
        meio_pagamento = "pix"
    elif "cartao" in texto or "cartão" in texto:
        meio_pagamento = "cartao"
    elif "dinheiro" in texto:
        meio_pagamento = "dinheiro"

    salvar_gasto(descricao, valor, categoria, meio_pagamento, schema)
    logger.info("Intenção identificada: registrar gasto (%s)", message.user_id)
    return AgentResponse(
        text=f"Anotado. Registrei R$ {valor:.2f} em {categoria}.",
        metadata={"intent": "registrar_gasto", "valor": valor, "categoria": categoria, "meio_pagamento": meio_pagamento},
    )


async def _responder_salario(message: IncomingMessage, session: SessionData) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(message.user_id)
    if schema:
        session.state["schema"] = schema
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": "salario"})
    logger.info("Intenção identificada: salário (%s)", message.user_id)
    return AgentResponse(text=registrar_salario(message.text or "", schema), metadata={"intent": "salario"})


async def _responder_lembretes(message: IncomingMessage, session: SessionData, texto_normalizado: str) -> AgentResponse:
    schema = session.state.get("schema") or obter_schema_por_telefone(message.user_id)
    if schema:
        session.state["schema"] = schema

    if texto_normalizado.startswith("lista lembretes") and schema:
        lembretes = listar_lembretes(message.user_id, schema)
        if not lembretes:
            return AgentResponse(text="📭 Você ainda não possui lembretes cadastrados.", metadata={"intent": "lembretes"})
        resposta = "📋 Seus lembretes:\n\n" + "\n".join([f"• {item['id']} - {item['mensagem']}\n⏰ CRON: {item['cron']}" for item in lembretes])
        return AgentResponse(text=resposta, metadata={"intent": "lembretes"})

    if texto_normalizado.startswith("apagar lembrete") and schema:
        partes = (message.text or "").split()
        if len(partes) >= 3 and partes[2].isdigit():
            sucesso = apagar_lembrete(message.user_id, int(partes[2]), schema)
            texto = "🗑️ Lembrete apagado com sucesso!" if sucesso else "⚠️ Lembrete não encontrado ou não pertence a você."
            return AgentResponse(text=texto, metadata={"intent": "lembretes"})
        return AgentResponse(text="❌ Formato inválido. Use: apagar lembrete [ID]", metadata={"intent": "lembretes"})

    if texto_normalizado.startswith("tabela cron"):
        return AgentResponse(
            text=(
                "⏰ Exemplos de expressões CRON:\n"
                "* * * * * → Executa a cada minuto\n"
                "0 9 * * * → Todos os dias às 09:00\n"
                "30 14 * * * → Todos os dias às 14:30\n"
                "0 8 * * 1-5 → Segunda a sexta às 08:00"
            ),
            metadata={"intent": "lembretes"},
        )

    if "lembra" in texto_normalizado or "lembrete" in texto_normalizado:
        return AgentResponse(
            text="Posso te ajudar com isso. Qual é a mensagem do lembrete e para quando você quer receber?",
            metadata={"intent": "lembrete_natural"},
        )

    return AgentResponse(text="❌ Formato inválido de lembrete.", metadata={"intent": "lembretes"})


async def _responder_noticias() -> AgentResponse:
    logger.info("Comando identificado: notícias")
    return AgentResponse(text=obter_boletim_the_news(), metadata={"intent": "noticias"})


async def _responder_email_compat() -> AgentResponse:
    logger.info("Comando identificado: e-mails")
    return AgentResponse(text="ℹ️ Fluxo de e-mail mantido no backend atual.", metadata={"intent": "emails"})


async def _responder_rota(texto: str) -> AgentResponse:
    logger.info("Comando identificado: rotas")
    partes = texto.split(maxsplit=1)
    if len(partes) < 2:
        return AgentResponse(text="Me diga o endereço de destino para eu calcular a rota.", metadata={"intent": "rotas"})
    resultado_rota = calcular_rota(partes[1].strip())
    if isinstance(resultado_rota, dict):
        return AgentResponse(text=resultado_rota.get("erro", "❌ Não foi possível calcular a rota."), metadata={"intent": "rotas"})
    return AgentResponse(text=str(resultado_rota), metadata={"intent": "rotas"})


async def _processar_texto_financeiro(message: IncomingMessage, session: SessionData) -> AgentResponse:
    texto_original = (message.text or "").strip()
    texto_normalizado = _normalizar_texto(texto_original)
    telefone = message.user_id
    schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
    if schema:
        session.state["schema"] = schema

    if message.channel == "whatsapp" and not verificar_autorizacao(telefone):
        return AgentResponse(text="🚫 Seu número ainda não está autorizado a usar o assistente financeiro.", metadata={"intent": "nao_autorizado"})

    if message.channel == "telegram" and not verificar_autorizacao(telefone):
        nome = message.metadata.get("display_name") or telefone.replace("telegram:", "telegram_")
        try:
            liberar_usuario(nome, telefone)
        except Exception as exc:
            logger.exception("Falha ao provisionar usuário Telegram: %s", exc)
        schema = obter_schema_por_telefone(telefone)
        if schema:
            session.state["schema"] = schema

    if session.state.get("etapa", "inicio") != "inicio" or _identificar_modo_grafica(texto_normalizado):
        resposta_grafica = await gerar_resposta_grafica(telefone, texto_original, "text", canal=message.channel, raw_payload=message.raw_payload)
        if resposta_grafica.response_type != "text" or resposta_grafica.text != "fluxo_grafica_inativo":
            session.state["current_intent"] = "grafica"
            return resposta_grafica

    intent = _identificar_intencao_deterministica(texto_original, texto_normalizado)
    session.state["current_intent"] = intent or "conversational_ai"

    if intent == "ajuda":
        return await _responder_ajuda(telefone)
    if intent == "total_gasto":
        return await _responder_total_gasto(telefone, session)
    if intent == "fatura_paga":
        return await _responder_fatura_paga(telefone, session)
    if intent == "graficos":
        return await _responder_graficos(telefone, session)
    if intent == "cep":
        return await _responder_cep(texto_original)
    if intent == "cotacao":
        return await _responder_cotacao(texto_original, texto_normalizado)
    if intent == "lembretes":
        return await _responder_lembretes(message, session, texto_normalizado)
    if intent == "noticias":
        return await _responder_noticias()
    if intent == "emails":
        return await _responder_email_compat()
    if intent == "rotas":
        return await _responder_rota(texto_original)
    if intent == "registrar_gasto":
        return await _responder_registrar_gasto(message, session)
    if intent == "salario":
        return await _responder_salario(message, session)

    logger.info("Intenção conversacional identificada para %s: %s", telefone, texto_original)
    resposta = await gerar_resposta_conversacional(message, session.state)
    resposta.metadata.setdefault("intent", "conversational_ai")
    return resposta


async def _processar_midia(message: IncomingMessage) -> AgentResponse:
    tipo = message.message_type
    caminho = message.metadata.get("local_path")
    if not caminho:
        return AgentResponse(text="⚠️ Mídia recebida, mas o arquivo não foi baixado corretamente.")

    if tipo == "image":
        from backend.services.leitura_service import (
            formatar_codigodebarras_para_whatsapp,
            formatar_qrcode_para_whatsapp,
            try_all_techniques,
        )

        resultado = try_all_techniques(caminho, message.metadata.get("media_key", "tmp"))
        if not resultado:
            return AgentResponse(text="⚠️ Não consegui extrair nenhuma informação da imagem.")
        if resultado.get("tipo", "").upper() == "QRCODE":
            texto = formatar_qrcode_para_whatsapp(resultado)
        else:
            texto = formatar_codigodebarras_para_whatsapp(resultado)
        return AgentResponse(text=texto, metadata={"parsed": resultado, "intent": "midia"})

    if tipo == "document":
        from backend.services.leitura_service import (
            formatar_codigodebarras_para_whatsapp,
            formatar_qrcode_para_whatsapp,
            processar_codigodebarras_com_pdfplumber,
            processar_qrcode_com_ocr,
        )

        file_name = (message.file_name or "").lower()
        if file_name.endswith(".pdf"):
            dados = processar_codigodebarras_com_pdfplumber(caminho)
        else:
            dados = processar_qrcode_com_ocr(caminho)
        if not dados:
            return AgentResponse(text="⚠️ Não consegui interpretar o documento.")
        texto = formatar_qrcode_para_whatsapp(dados)
        if "nfe" in file_name:
            texto = formatar_codigodebarras_para_whatsapp(dados)
        return AgentResponse(text=texto, metadata={"parsed": dados, "intent": "midia"})

    if tipo == "audio":
        return AgentResponse(text="⚠️ Áudio ainda não ativado neste núcleo.", metadata={"intent": "midia"})

    return AgentResponse(text="⚠️ Tipo de mídia não suportado.", metadata={"intent": "midia"})


async def route_incoming_message(message: IncomingMessage, session: SessionData) -> AgentResponse:
    if message.message_type == "location":
        try:
            latitude, longitude = (message.text or "").split(",", 1)
            salvar_localizacao_usuario(message.user_id, float(latitude), float(longitude))
            session.state["current_intent"] = "location"
            return AgentResponse(text="📍 Obrigado por compartilhar sua localização!", metadata={"intent": "location"})
        except Exception:
            return AgentResponse(text="⚠️ Não consegui interpretar sua localização.", metadata={"intent": "location"})

    if message.message_type in {"image", "document", "audio"}:
        return await _processar_midia(message)

    return await _processar_texto_financeiro(message, session)
