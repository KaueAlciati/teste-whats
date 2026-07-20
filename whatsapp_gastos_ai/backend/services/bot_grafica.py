from __future__ import annotations

import logging
from typing import Any

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.sessions import session_store
from backend.services.chatwoot_integration import transferir_para_vendedor
from backend.services.whatsapp_service import (
    enviar_imagem_whatsapp,
    enviar_lista_interativa,
    enviar_mensagem_whatsapp,
)

logger = logging.getLogger(__name__)

# Compatibilidade com o código antigo
sessoes = session_store._sessions


def _session_state(canal: str, telefone: str) -> dict[str, Any]:
    return session_store.get(canal, telefone).state


async def verificar_handoff(telefone: str, canal: str = "whatsapp") -> bool:
    return bool(_session_state(canal, telefone).get("handoff"))


async def marcar_handoff(telefone: str, canal: str = "whatsapp"):
    _session_state(canal, telefone)["handoff"] = True


def _eh_fluxo_grafica(texto: str, sessao: dict[str, Any]) -> bool:
    texto = (texto or "").strip().lower()
    etapa = sessao.get("etapa", "inicio")
    return etapa != "inicio" or texto in {"atendimento", "gráfica", "grafica", "orçamento gráfica", "orcamento grafica"}


def _resposta_opcoes() -> AgentResponse:
    return AgentResponse(
        text="Olá! 👋 Bem-vindo à Gráfica XP\nQual produto você precisa?",
        response_type="options",
        options=[
            {"id": "cartao", "label": "Cartão de visita", "description": "500un a partir de R$50"},
            {"id": "banner", "label": "Banner", "description": "Diversos tamanhos"},
            {"id": "panfleto", "label": "Panfleto/Flyer", "description": "A partir de 1000un"},
            {"id": "adesivo", "label": "Adesivo", "description": "Personalizados"},
            {"id": "outro", "label": "Outro produto", "description": "Falar com vendedor"},
        ],
        metadata={"stage": "inicio"},
    )


async def _processar_fluxo_grafica(telefone: str, mensagem: str, tipo_mensagem: str = "text", canal: str = "whatsapp") -> AgentResponse:
    sessao = _session_state(canal, telefone)
    etapa = sessao.get("etapa", "inicio")
    texto = (mensagem or "").strip()
    texto_lower = texto.lower()

    if sessao.get("handoff"):
        return AgentResponse(text="⏭️ Conversa em atendimento humano.", transfer_to_human=True)

    if etapa == "inicio":
        sessao["etapa"] = "aguardando_produto"
        sessao.setdefault("dados", {})
        return _resposta_opcoes()

    if etapa == "aguardando_produto":
        if texto_lower == "outro":
            sessao["handoff"] = True
            dados = sessao.get("dados", {})
            dados["produto"] = "outro"
            sessao["dados"] = dados
            return AgentResponse(
                text="Sem problemas! Vou te passar para um vendedor agora 😊",
                transfer_to_human=True,
                metadata={"produto": "outro"},
            )

        sessao.setdefault("dados", {})["produto"] = texto_lower
        sessao["etapa"] = "aguardando_quantidade"
        return AgentResponse(text=f"Ótimo! Você escolheu: {texto_upper(texto_lower)}\n\nQuantas unidades você precisa?")

    if etapa == "aguardando_quantidade":
        try:
            quantidade = int(texto.strip())
        except ValueError:
            return AgentResponse(text="Por favor, envie apenas o número de unidades (ex: 500)")
        sessao.setdefault("dados", {})["quantidade"] = quantidade
        sessao["etapa"] = "aguardando_prazo"
        return AgentResponse(text=f"Perfeito! {quantidade} unidades.\n\nPara quando você precisa? (ex: 5 dias, 1 semana)")

    if etapa == "aguardando_prazo":
        sessao.setdefault("dados", {})["prazo"] = texto
        sessao["etapa"] = "aguardando_arte"
        return AgentResponse(text="Entendi! Última pergunta:\n\nVocê já tem a arte pronta?\n\n1️⃣ Sim, tenho\n2️⃣ Não, preciso de ajuda")

    if etapa == "aguardando_arte":
        sessao.setdefault("dados", {})["arte_pronta"] = "Sim" if texto_lower in {"1", "sim", "tenho"} else "Não, precisa de ajuda"
        dados = sessao["dados"]
        sessao["handoff"] = True
        try:
            conversation_id = await transferir_para_vendedor(telefone, dados)
        except Exception:
            conversation_id = None
        if conversation_id:
            return AgentResponse(
                text="Perfeito! 😊 Vou te encaminhar para um vendedor que vai passar o orçamento e detalhes.\n\nAguarde um momento...",
                transfer_to_human=True,
                metadata={"conversation_id": conversation_id, "dados": dados},
            )
        return AgentResponse(
            text="Aguarde um momento. Tive um erro ao conectar com o vendedor, mas seu atendimento foi separado para acompanhamento.",
            transfer_to_human=True,
            metadata={"dados": dados},
        )

    sessao["etapa"] = "inicio"
    return _resposta_opcoes()


def texto_upper(texto: str) -> str:
    return texto.upper() if texto else texto


async def gerar_resposta_bot(usuario_id: str, mensagem: str, tipo: str = "text", canal: str = "whatsapp", raw_payload: dict | None = None) -> AgentResponse:
    sessao = _session_state(canal, usuario_id)
    if not _eh_fluxo_grafica(mensagem, sessao):
        return AgentResponse(text="fluxo_grafica_inativo")
    return await _processar_fluxo_grafica(usuario_id, mensagem, tipo, canal=canal)


async def _enviar_resposta_whatsapp(telefone: str, resposta: AgentResponse):
    if resposta.transfer_to_human:
        return

    if resposta.response_type == "options" and resposta.options:
        opcoes = [
            {"id": str(item.get("id")), "title": str(item.get("label") or item.get("title") or item.get("id"))}
            for item in resposta.options
        ]
        if len(opcoes) <= 3:
            await enviar_mensagem_whatsapp(telefone, resposta.text or "")
            await enviar_mensagem_whatsapp(telefone, "\n".join(f"- {o['title']}" for o in opcoes))
        else:
            secoes = [{"title": "Opções", "rows": [{"id": o["id"], "title": o["title"]} for o in opcoes]}]
            await enviar_lista_interativa(telefone, "Opções", resposta.text or "", "Ver opções", secoes)
        return

    if resposta.image_path:
        await enviar_imagem_whatsapp(telefone, resposta.image_path, resposta.text)
        return

    if resposta.document_path:
        await enviar_mensagem_whatsapp(telefone, resposta.text or "Documento gerado.")
        return

    await enviar_mensagem_whatsapp(telefone, resposta.text or "")


async def processar_mensagem_bot(telefone: str, mensagem: str, tipo_mensagem: str = "text"):
    """
    Adaptador de compatibilidade para o fluxo antigo do WhatsApp.
    """
    resposta = await gerar_resposta_bot(telefone, mensagem, tipo_mensagem, canal="whatsapp")
    await _enviar_resposta_whatsapp(telefone, resposta)
    return resposta


async def processar_webhook_whatsapp(webhook_data: dict):
    """
    Mantido por compatibilidade. O webhook principal agora normaliza e roteia no main.
    """
    logger.info("Webhook WhatsApp recebido para compatibilidade.")
    return webhook_data
