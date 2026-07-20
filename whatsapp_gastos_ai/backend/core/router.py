from __future__ import annotations

import logging
import os
import re
from typing import Any

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.pending_intent_resolver import PendingResolution, resolve_pending_intent
from backend.core.sessions import SessionData, session_store
from backend.core.intent_classifier import IntentResult, classify_intent
from backend.core.text_normalizer import normalize_user_text, remove_accents_for_matching
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
from backend.services.report_service import gerar_pdf_financeiro
from backend.services.scheduler import agendar_lembrete_cron
from backend.services.token_service import gerar_token_acesso
from backend.services.email_service import buscar_credenciais_email, formatar_emails_para_whatsapp, get_emails_info, listar_emails_cadastrados, salvar_credenciais_email
from backend.utils import obter_schema_por_telefone, salvar_localizacao_usuario

logger = logging.getLogger(__name__)


def _normalizar_texto(texto: str) -> str:
    return remove_accents_for_matching(normalize_user_text(texto))


def _question_key(texto: str | None) -> str:
    return _normalizar_texto(texto or "")


def _ajustar_pergunta_repetida(session: SessionData, question: str, field: str | None = None) -> str:
    last_question = _question_key(session.state.get("last_question"))
    new_question = _question_key(question)
    last_field = session.state.get("last_question_field")
    if last_question and last_question == new_question and (field is None or last_field == field):
        if field == "period":
            return "Me diz se é deste mês, do mês passado ou de outro período."
        if field == "measurement":
            return "Qual seria a medida aproximada?"
        if field == "quantity":
            return "Quantas unidades você precisa?"
        return "Me manda só essa informação para eu continuar."
    return question


def _registrar_pergunta_pendente(session: SessionData, question: str, field: str | None = None, user_answer: str | None = None) -> None:
    session_store.set_pending_context(session.channel, session.user_id, question=question, field=field, user_answer=user_answer)


async def _tratar_pendente(message: IncomingMessage, session: SessionData, texto_original: str, texto_normalizado: str) -> AgentResponse | None:
    pending_intent = session.state.get("pending_intent")
    if not pending_intent:
        return None

    resolution: PendingResolution = await resolve_pending_intent(session, texto_original, texto_normalizado)
    if resolution.cancel_intent:
        session_store.clear_pending_intent(message.channel, message.user_id)
        session.state["current_intent"] = None
        return AgentResponse(text="Tudo bem, posso seguir com outra solicitação.", metadata={"intent": "cancelled"})

    if not resolution.matched:
        if resolution.clarification_question:
            question = _ajustar_pergunta_repetida(session, resolution.clarification_question, (resolution.remaining_fields or [None])[0])
            _registrar_pergunta_pendente(session, question, (resolution.remaining_fields or [None])[0], texto_original)
            session_store.set_pending_intent(
                message.channel,
                message.user_id,
                pending_intent,
                parameters=resolution.parameters,
                missing_fields=resolution.remaining_fields,
                clarification_question=question,
            )
            return AgentResponse(text=question, metadata={"intent": pending_intent, "pending": True})
        return None

    params = dict(resolution.parameters or {})
    session.state["collected_parameters"] = params
    session_store.update_pending_parameters(
        message.channel,
        message.user_id,
        parameters=params,
        missing_fields=resolution.remaining_fields,
        clarification_question=resolution.clarification_question,
    )
    if resolution.remaining_fields:
        question = _ajustar_pergunta_repetida(session, resolution.clarification_question or "Pode me passar mais um detalhe?", resolution.remaining_fields[0])
        _registrar_pergunta_pendente(session, question, resolution.remaining_fields[0], texto_original)
        session_store.set_pending_intent(
            message.channel,
            message.user_id,
            pending_intent,
            parameters=params,
            missing_fields=resolution.remaining_fields,
            clarification_question=question,
        )
        return AgentResponse(text=question, metadata={"intent": pending_intent, "pending": True})

    resultado = IntentResult(
        intent=pending_intent,  # type: ignore[arg-type]
        confidence=0.99,
        parameters=params,
        missing_fields=[],
        should_execute=True,
        clarification_question=None,
    )
    session_store.clear_pending_intent(message.channel, message.user_id)
    return await _responder_intencao_classificada(message, session, resultado)


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


def _comando_exato(texto_normalizado: str) -> str | None:
    if texto_normalizado in {"ajuda", "menu", "comandos"}:
        return "help"
    if texto_normalizado == "total gasto":
        return "get_total_expense"
    if texto_normalizado in {"fatura paga", "fatura paga!"}:
        return "fatura_paga"
    if texto_normalizado in {"gráficos", "graficos"}:
        return "graficos"
    if texto_normalizado in {"cotação", "cotacao"}:
        return "get_exchange_rate"
    if texto_normalizado == "listar moedas":
        return "listar_moedas"
    if texto_normalizado == "listar conversoes":
        return "listar_conversoes"
    if texto_normalizado.startswith("cep "):
        return "lookup_zipcode"
    if texto_normalizado.startswith("conversoes "):
        return "listar_conversoes_moeda"
    if texto_normalizado.startswith("lista lembretes"):
        return "list_reminders"
    if texto_normalizado.startswith("apagar lembrete"):
        return "delete_reminder"
    if texto_normalizado.startswith("noticias") or texto_normalizado.startswith("notícias"):
        return "get_news"
    if texto_normalizado.startswith("email") or texto_normalizado.startswith("e-mails") or texto_normalizado.startswith("emails"):
        return "get_email_summary"
    if texto_normalizado.startswith("rota ") or texto_normalizado.startswith("rotas "):
        return "get_route"
    if texto_normalizado.startswith("salario ") or texto_normalizado.startswith("salário "):
        return "register_salary"
    return None


def _categoria_gasto(texto: str) -> str:
    texto = _normalizar_texto(texto)
    if any(palavra in texto for palavra in {"almoco", "almoço", "jantar", "cafe", "lanche", "mercado", "supermercado"}):
        return "alimentacao"
    if any(palavra in texto for palavra in {"uber", "taxi", "transporte", "combustivel", "gasolina"}):
        return "transporte"
    if any(palavra in texto for palavra in {"internet", "celular", "assinatura", "streaming"}):
        return "servicos"
    return "geral"


def _converter_periodo_para_cron(periodo: str | None, horario: str | None) -> str | None:
    if not periodo or not horario:
        return None
    if periodo == "tomorrow":
        from datetime import datetime, timedelta

        amanha = datetime.now().date() + timedelta(days=1)
        hora_minuto = horario.strip().replace("h", ":")
        partes = hora_minuto.split(":")
        hora = int(partes[0])
        minuto = int(partes[1]) if len(partes) > 1 and partes[1] else 0
        return f"{minuto} {hora} {amanha.day} {amanha.month} *"
    return None


async def _responder_intencao_classificada(message: IncomingMessage, session: SessionData, resultado: IntentResult) -> AgentResponse:
    telefone = message.user_id
    texto_original = (message.text or "").strip()
    params = dict(session.state.get("collected_parameters") or {})
    params.update(resultado.parameters or {})

    if resultado.intent in {"greeting", "general_conversation"}:
        session_store.clear_pending_intent(message.channel, telefone)
        session.state["current_intent"] = resultado.intent
        if resultado.intent == "greeting":
            return AgentResponse(text="Oi! Tudo certo? Me conta no que você precisa de ajuda.", metadata={"intent": "greeting"})
        resposta = await gerar_resposta_conversacional(message, session.state)
        resposta.metadata.setdefault("intent", "general_conversation")
        return resposta

    if resultado.intent == "help":
        session_store.clear_pending_intent(message.channel, telefone)
        session.state["current_intent"] = "help"
        return await _responder_ajuda(telefone)

    if resultado.intent == "human_support":
        session_store.clear_pending_intent(message.channel, telefone)
        session.state["current_intent"] = "human_support"
        return AgentResponse(text="Certo. Vou encaminhar seu pedido para atendimento humano.", transfer_to_human=True, metadata={"intent": "human_support"})

    if resultado.intent == "unknown":
        session.state["current_intent"] = "unknown"
        question = resultado.clarification_question or "Você quer ajuda com finanças, gráfica, lembretes, cotação ou relatórios?"
        return AgentResponse(text=question, metadata={"intent": "unknown"})

    if resultado.intent == "generate_financial_pdf":
        session.state["current_intent"] = resultado.intent
        if not resultado.should_execute:
            pergunta = resultado.clarification_question or "Você quer o relatório deste mês ou de outro período?"
            session_store.set_pending_intent(
                message.channel,
                telefone,
                "generate_financial_pdf",
                parameters=params,
                missing_fields=resultado.missing_fields,
                clarification_question=pergunta,
            )
            session.state["collected_parameters"] = params
            _registrar_pergunta_pendente(session, pergunta, "period", texto_original)
            return AgentResponse(text=pergunta, metadata={"intent": resultado.intent})

        schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
        if not schema:
            return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": resultado.intent})
        session_store.clear_pending_intent(message.channel, telefone)
        session.state["collected_parameters"] = params
        periodo = params.get("period")
        pdf_info = gerar_pdf_financeiro(schema, periodo=periodo)
        return AgentResponse(
            text=f"Pronto. Gerei o relatório financeiro de {pdf_info['period_label']}.",
            response_type="document",
            document_path=pdf_info["path"],
            document_name=pdf_info["name"],
            metadata={"intent": resultado.intent, "period": pdf_info["period_label"], "total": pdf_info["total"]},
        )

    if resultado.intent == "graphic_product_question":
        session_store.clear_pending_intent(message.channel, telefone)
        session.state["current_intent"] = resultado.intent
        return AgentResponse(text="Posso te ajudar com adesivos, banners, placas, fachadas e outros materiais. Me diga o produto que você quer orçar.", metadata={"intent": resultado.intent})

    if resultado.intent == "graphic_quote":
        session.state["current_intent"] = resultado.intent
        session.state["collected_parameters"] = params
        if not resultado.should_execute:
            missing = resultado.missing_fields or []
            pergunta = resultado.clarification_question or "Certo. Me passa a medida para eu continuar."
            if "measurement" in missing:
                session.state["etapa"] = "aguardando_medida"
                session.state.setdefault("dados", {})["produto"] = params.get("product") or "produto"
            elif "quantity" in missing:
                session.state["etapa"] = "aguardando_quantidade"
                session.state.setdefault("dados", {})["produto"] = params.get("product") or session.state.get("dados", {}).get("produto", "produto")
                if params.get("measurement"):
                    session.state.setdefault("dados", {})["medida"] = params["measurement"]
            else:
                session.state["etapa"] = "aguardando_produto"
            session_store.set_pending_intent(
                message.channel,
                telefone,
                "graphic_quote",
                parameters=params,
                missing_fields=resultado.missing_fields,
                clarification_question=pergunta,
            )
            _registrar_pergunta_pendente(session, pergunta, missing[0] if missing else None, texto_original)
            return AgentResponse(text=pergunta, metadata={"intent": resultado.intent, "pending": True})

        session_store.clear_pending_intent(message.channel, telefone)
        if session.state.get("etapa") in {"aguardando_medida", "aguardando_quantidade", "aguardando_prazo", "aguardando_arte"}:
            resposta_grafica = await gerar_resposta_grafica(telefone, texto_original, "text", canal=message.channel, raw_payload=message.raw_payload)
            if resposta_grafica.response_type != "text" or resposta_grafica.text != "fluxo_grafica_inativo":
                return resposta_grafica
        return AgentResponse(text="Certo. Me conta a medida do material para eu continuar.", metadata={"intent": resultado.intent})

    if resultado.intent in {"register_expense", "register_salary", "get_total_expense", "get_exchange_rate", "lookup_zipcode", "get_route", "get_news", "get_email_summary", "list_reminders", "delete_reminder"}:
        session_store.clear_pending_intent(message.channel, telefone)

    if resultado.intent == "register_expense":
        schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
        if not schema:
            return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": resultado.intent})
        if not resultado.should_execute:
            pergunta = resultado.clarification_question or "Entendi. Quanto foi o gasto?"
            session_store.set_pending_intent(
                message.channel,
                telefone,
                "register_expense",
                parameters=params,
                missing_fields=resultado.missing_fields,
                clarification_question=pergunta,
            )
            session.state["collected_parameters"] = params
            _registrar_pergunta_pendente(session, pergunta, (resultado.missing_fields or ["value"])[0], texto_original)
            return AgentResponse(text=pergunta, metadata={"intent": resultado.intent})
        valor = params.get("value")
        if valor is None:
            match = re.search(r"(?:r\$|rs)?\s*(\d+(?:[.,]\d{1,2})?)", texto_original, flags=re.IGNORECASE)
            valor = float(match.group(1).replace(",", ".")) if match else None
        if valor is None:
            return AgentResponse(text="Quanto foi o gasto? Me manda o valor que eu registro.", metadata={"intent": resultado.intent})
        descricao = params.get("description") or texto_original
        meio_pagamento = params.get("payment_method") or "não informado"
        categoria = params.get("category") or _categoria_gasto(descricao)
        salvar_gasto(descricao, float(valor), categoria, meio_pagamento, schema)
        session.state["collected_parameters"] = params
        return AgentResponse(
            text=f"Anotado. Registrei R$ {float(valor):.2f} em {categoria}.",
            metadata={"intent": resultado.intent, "valor": float(valor), "categoria": categoria, "meio_pagamento": meio_pagamento},
        )

    if resultado.intent == "register_salary":
        schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
        if not schema:
            return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": resultado.intent})
        session.state["collected_parameters"] = params
        return AgentResponse(text=registrar_salario(texto_original, schema), metadata={"intent": resultado.intent})

    if resultado.intent == "get_total_expense":
        schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
        if not schema:
            return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": resultado.intent})
        total = calcular_total_gasto(schema)
        session.state["collected_parameters"] = params
        return AgentResponse(text=f"📊 Total gasto no mês: R$ {format(total, ',.2f').replace(',', '.')}", metadata={"intent": resultado.intent, "period": params.get("period", "current_month")})

    if resultado.intent == "get_exchange_rate":
        session.state["collected_parameters"] = params
        if params.get("currency") and params["currency"] not in {"USD", "EUR", "GBP", "JPY", "ARS"}:
            return AgentResponse(text="Qual moeda você quer consultar? Exemplo: dólar, euro ou libra.", metadata={"intent": resultado.intent})
        if params.get("currency"):
            return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, params["currency"]), metadata={"intent": resultado.intent})
        return AgentResponse(text=obter_cotacao_principais(os.getenv("API_COTACAO"), MOEDA_EMOJIS), metadata={"intent": resultado.intent})

    if resultado.intent == "lookup_zipcode":
        session.state["collected_parameters"] = params
        match = re.search(r"\b(\d{8})\b", texto_original)
        if match:
            return AgentResponse(text=buscar_cep(match.group(1)), metadata={"intent": resultado.intent})
        return AgentResponse(text="Me manda o CEP com 8 números para eu consultar.", metadata={"intent": resultado.intent})

    if resultado.intent == "get_route":
        session.state["collected_parameters"] = params
        return await _responder_rota(texto_original)

    if resultado.intent == "get_news":
        session.state["collected_parameters"] = params
        return await _responder_noticias()

    if resultado.intent == "get_email_summary":
        session.state["collected_parameters"] = params
        return await _responder_email_compat()

    if resultado.intent == "list_reminders":
        session.state["collected_parameters"] = params
        texto_normalizado = _normalizar_texto(texto_original)
        return await _responder_lembretes(message, session, texto_normalizado)

    if resultado.intent == "delete_reminder":
        session.state["collected_parameters"] = params
        texto_normalizado = _normalizar_texto(texto_original)
        return await _responder_lembretes(message, session, texto_normalizado)

    if resultado.intent == "create_reminder":
        session.state["collected_parameters"] = params
        if not resultado.should_execute:
            pergunta = resultado.clarification_question or "Certo. Me diz o que você quer lembrar."
            session_store.set_pending_intent(
                message.channel,
                telefone,
                "create_reminder",
                parameters=params,
                missing_fields=resultado.missing_fields,
                clarification_question=pergunta,
            )
            _registrar_pergunta_pendente(session, pergunta, (resultado.missing_fields or [None])[0], texto_original)
            return AgentResponse(text=pergunta, metadata={"intent": resultado.intent})
        cron_expr = params.get("cron") or _converter_periodo_para_cron(params.get("date"), params.get("time"))
        if not cron_expr:
            session_store.set_pending_intent(
                message.channel,
                telefone,
                "create_reminder",
                parameters=params,
                missing_fields=["time"],
                clarification_question="Qual horário você quer para o lembrete?",
            )
            return AgentResponse(text="Qual horário você quer para o lembrete?", metadata={"intent": resultado.intent})
        mensagem_lembrete = params.get("text") or texto_original
        agendar_lembrete_cron(telefone, mensagem_lembrete, cron_expr)
        session_store.clear_pending_intent(message.channel, telefone)
        return AgentResponse(text=f"⏰ Lembrete agendado com sucesso!\nMensagem: \"{mensagem_lembrete}\"", metadata={"intent": resultado.intent})

    logger.info("Intenção conversacional identificada para %s: %s", telefone, texto_original)
    resposta = await gerar_resposta_conversacional(message, session.state)
    resposta.metadata.setdefault("intent", "conversational_ai")
    return resposta


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

    pendente_atual = session.state.get("pending_intent")
    resposta_pendente = await _tratar_pendente(message, session, texto_original, texto_normalizado)
    if resposta_pendente is not None:
        session.state["current_intent"] = pendente_atual
        return resposta_pendente

    if session.state.get("etapa", "inicio") != "inicio" and not session.state.get("pending_intent"):
        resposta_grafica = await gerar_resposta_grafica(telefone, texto_original, "text", canal=message.channel, raw_payload=message.raw_payload)
        if resposta_grafica.response_type != "text" or resposta_grafica.text != "fluxo_grafica_inativo":
            session.state["current_intent"] = "graphic_quote"
            return resposta_grafica

    comando_exato = _comando_exato(texto_normalizado)
    if comando_exato == "help":
        session.state["current_intent"] = "help"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_ajuda(telefone)
    if comando_exato == "get_total_expense":
        session.state["current_intent"] = "get_total_expense"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_total_gasto(telefone, session)
    if comando_exato == "fatura_paga":
        session.state["current_intent"] = "fatura_paga"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_fatura_paga(telefone, session)
    if comando_exato == "graficos":
        session.state["current_intent"] = "graficos"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_graficos(telefone, session)
    if comando_exato == "get_exchange_rate":
        session.state["current_intent"] = "get_exchange_rate"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_cotacao(texto_original, texto_normalizado)
    if comando_exato == "lookup_zipcode":
        session.state["current_intent"] = "lookup_zipcode"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_cep(texto_original)
    if comando_exato == "get_news":
        session.state["current_intent"] = "get_news"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_noticias()
    if comando_exato == "get_email_summary":
        session.state["current_intent"] = "get_email_summary"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_email_compat()
    if comando_exato == "get_route":
        session.state["current_intent"] = "get_route"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_rota(texto_original)
    if comando_exato == "register_salary":
        session.state["current_intent"] = "register_salary"
        session_store.clear_pending_intent(message.channel, telefone)
        return await _responder_salario(message, session)
    if comando_exato == "list_reminders":
        resultado = IntentResult(intent="list_reminders", confidence=1.0, parameters={}, missing_fields=[], should_execute=True)
        return await _responder_intencao_classificada(message, session, resultado)
    if comando_exato == "delete_reminder":
        resultado = IntentResult(intent="delete_reminder", confidence=1.0, parameters={"raw_text": texto_original}, missing_fields=["id"], should_execute=False, clarification_question="Qual é o ID do lembrete que você quer apagar?")
        return await _responder_intencao_classificada(message, session, resultado)
    if comando_exato == "listar_moedas":
        session.state["current_intent"] = "get_exchange_rate"
        session_store.clear_pending_intent(message.channel, telefone)
        return AgentResponse(text=listar_moedas_disponiveis(MOEDAS), metadata={"intent": "get_exchange_rate"})
    if comando_exato == "listar_conversoes":
        session.state["current_intent"] = "get_exchange_rate"
        session_store.clear_pending_intent(message.channel, telefone)
        return AgentResponse(text=listar_conversoes_disponiveis(CONVERSOES), metadata={"intent": "get_exchange_rate"})
    if comando_exato == "listar_conversoes_moeda":
        partes = texto_original.split()
        if len(partes) == 2:
            moeda = partes[1].upper()
            if moeda in CONVERSOES:
                return AgentResponse(text=listar_conversoes_disponiveis_moeda(CONVERSOES, moeda), metadata={"intent": "get_exchange_rate"})
        return AgentResponse(text=f"⚠️ Moeda '{partes[1].upper() if len(partes) > 1 else ''}' não encontrada ou não tem conversões disponíveis.", metadata={"intent": "get_exchange_rate"})

    resultado_intencao = await classify_intent(message, session.state)
    session.state["current_intent"] = resultado_intencao.intent
    logger.info("Intenção classificada para %s: %s (%.2f)", telefone, resultado_intencao.intent, resultado_intencao.confidence)
    return await _responder_intencao_classificada(message, session, resultado_intencao)


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
