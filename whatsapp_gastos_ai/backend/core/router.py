from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.sessions import SessionData, session_store
from backend.services.bot_grafica import gerar_resposta_bot as gerar_resposta_grafica
from backend.services.api_service import (
    MOEDAS,
    CONVERSOES,
    MOEDA_EMOJIS,
    buscar_cep,
    listar_conversoes_disponiveis,
    listar_conversoes_disponiveis_moeda,
    listar_moedas_disponiveis,
    obter_cotacao,
    obter_cotacao_principais,
)
from backend.services.autorizacao_service import verificar_autorizacao, liberar_usuario
from backend.services.email_service import (
    buscar_credenciais_email,
    formatar_emails_para_whatsapp,
    get_emails_info,
    listar_emails_cadastrados,
    salvar_credenciais_email,
)
from backend.services.gastos_service import (
    apagar_lembrete,
    calcular_total_gasto,
    listar_lembretes,
    pagar_fatura,
    registrar_salario,
)
from backend.services.leitura_service import (
    formatar_codigodebarras_para_whatsapp,
)
from backend.services.leitura_service import (
    formatar_codigodebarras_para_whatsapp,
    formatar_qrcode_para_whatsapp,
    gerar_descricao_para_classificacao,
    gerar_imagem_tabela,
    processar_codigodebarras_com_pdfplumber,
    processar_qrcode_com_ocr,
    try_all_techniques,
)
from backend.services.maps_service import calcular_rota
from backend.services.noticias_service import obter_boletim_the_news
from backend.services.scheduler import agendar_lembrete_cron
from backend.services.token_service import gerar_token_acesso
from backend.utils import obter_schema_por_telefone, salvar_localizacao_usuario

logger = logging.getLogger(__name__)


def _ajuda_texto(is_admin: bool = False) -> str:
    comandos = [
        "ajuda -> Mostra este menu",
        "total gasto -> Exibe o total de gastos do mês",
        "gráficos -> Envia um link com os gráficos financeiros",
        "fatura paga! -> Registra que a fatura foi paga",
        "cotação -> Mostra as principais moedas do dia",
        "listar moedas -> Lista moedas disponíveis",
        "listar conversoes -> Lista conversões disponíveis",
        "cotação USD -> Cotação de moeda específica",
        "cotação USD-EUR -> Conversão entre moedas",
        "cep 05424020 -> Consulta endereço pelo CEP",
        "lembrete: \"msg\" cron: 0 9 * * 1-5 -> Agenda lembrete",
        "tabela cron -> Exemplos de cron",
        "lista lembretes -> Lista lembretes do usuário",
        "apagar lembrete 1 -> Remove lembrete",
        "notícias -> Resumo do boletim",
        "email: ... -> Salva credenciais de e-mail",
        "resumo dos emails -> Lista e-mails recentes",
        "rota [endereço] -> Calcula rota",
    ]
    if is_admin:
        comandos.extend([
            "liberar [telefone] [nome] -> Autoriza usuário",
            "revogar [telefone] -> Revoga autorização",
        ])
    return "📌 Comandos disponíveis:\n\n" + "\n".join(f"• `{item}`" for item in comandos)


def _parse_lembrete(mensagem: str) -> tuple[str, str] | None:
    import re

    padrao = r'lembrete:\s*"(.+?)"\s*cron:\s*([0-9*/,\- ]{5,})'
    match = re.search(padrao, mensagem.lower())
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


async def _processar_texto_financeiro(message: IncomingMessage, session: SessionData) -> AgentResponse:
    text = (message.text or "").strip()
    lower = text.lower()
    partes = text.split()
    telefone = message.user_id
    schema = session.state.get("schema") or obter_schema_por_telefone(telefone)
    if schema:
        session.state["schema"] = schema

    if message.channel == "whatsapp" and not verificar_autorizacao(telefone):
        return AgentResponse(text="🚫 Seu número ainda não está autorizado a usar o assistente financeiro.")

    if message.channel == "telegram" and not verificar_autorizacao(telefone):
        # Provisiona Telegram na primeira mensagem para permitir testes sem WhatsApp.
        nome = message.metadata.get("display_name") or telefone.replace("telegram:", "telegram_")
        try:
            liberar_usuario(nome, telefone)
        except Exception as exc:
            logger.exception("Falha ao provisionar usuário Telegram: %s", exc)
        schema = obter_schema_por_telefone(telefone)
        if schema:
            session.state["schema"] = schema

    if session.state.get("etapa", "inicio") != "inicio" or lower in {"atendimento", "gráfica", "grafica", "orçamento gráfica", "orcamento grafica"}:
        resposta = await gerar_resposta_grafica(telefone, text, "text", canal=message.channel, raw_payload=message.raw_payload)
        if resposta.response_type != "text" or resposta.text != "fluxo_grafica_inativo":
            return resposta

    if lower in {"ajuda", "menu", "comandos"}:
        return AgentResponse(text=_ajuda_texto(is_admin=telefone == os.getenv("ADMIN_PHONE")))

    if lower == "total gasto":
        if not schema:
            schema = session.state.get("schema")
        total = calcular_total_gasto(schema) if schema else 0.0
        return AgentResponse(text=f"📊 Total gasto no mês: R$ {format(total, ',.2f').replace(',', '.')}")

    if lower == "fatura paga!":
        if schema:
            pagar_fatura(schema)
        return AgentResponse(text="✅ Todas as compras parceladas deste mês foram adicionadas ao total de gastos!")

    if lower.startswith("salario "):
        if schema:
            resposta = registrar_salario(text, schema)
        else:
            resposta = "❌ Usuário sem schema vinculado."
        return AgentResponse(text=resposta)

    if lower == "gráficos":
        if schema:
            token_info = gerar_token_acesso(telefone)
            token = token_info["token"]
            expira_em = token_info["expira_em"]
            resposta = (
                "📊 Aqui está o seu link com os gráficos financeiros!\n\n"
                f"🔗 https://dashboard-financas.up.railway.app/?phone={telefone}&token={token}\n"
                f"⚠️ O link é válido até às {expira_em.strftime('%H:%M')} por segurança."
            )
            return AgentResponse(text=resposta, metadata={"token": token})
        return AgentResponse(text="❌ Usuário sem schema vinculado.")

    if lower.startswith("cep "):
        if len(partes) == 2 and partes[1].isdigit():
            return AgentResponse(text=buscar_cep(partes[1]))
        return AgentResponse(text="❌ Formato inválido. Use: `cep 05424020` (apenas números).")

    if lower == "cotação":
        return AgentResponse(text=obter_cotacao_principais(os.getenv("API_COTACAO"), MOEDA_EMOJIS))

    if lower.startswith("cotação") and len(partes) == 2:
        return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, partes[1].upper()))

    if lower.startswith("cotação") and ("-" in lower or len(partes) > 2):
        moeda_origem = partes[1].upper() if len(partes) > 1 else "BRL"
        moeda_destino = partes[3].upper() if len(partes) > 3 else "BRL"
        return AgentResponse(text=obter_cotacao(os.getenv("API_COTACAO"), MOEDAS, CONVERSOES, moeda_origem, moeda_destino))

    if lower == "listar moedas":
        return AgentResponse(text=listar_moedas_disponiveis(MOEDAS))

    if lower == "listar conversoes":
        return AgentResponse(text=listar_conversoes_disponiveis(CONVERSOES))

    if lower.startswith("conversoes "):
        if len(partes) == 2:
            moeda = partes[1].upper()
            if moeda in CONVERSOES:
                return AgentResponse(text=listar_conversoes_disponiveis_moeda(CONVERSOES, moeda))
            return AgentResponse(text=f"⚠️ Moeda '{moeda}' não encontrada ou não tem conversões disponíveis.")
        return AgentResponse(text="❌ Formato inválido. Use: conversoes [moeda]")

    if lower.startswith("lembrete:") and "cron:" in lower:
        parsed = _parse_lembrete(text)
        if parsed:
            lembrete_texto, cron_expr = parsed
            agendar_lembrete_cron(telefone, lembrete_texto, cron_expr)
            return AgentResponse(text=f'⏰ Lembrete agendado com sucesso!\nMensagem: "{lembrete_texto}"')
        return AgentResponse(text="❌ Formato inválido de lembrete.")

    if lower == "tabela cron":
        return AgentResponse(text=(
            "⏰ Exemplos de expressões CRON:\n"
            "* * * * * → Executa a cada minuto\n"
            "0 9 * * * → Todos os dias às 09:00\n"
            "30 14 * * * → Todos os dias às 14:30\n"
            "0 8 * * 1-5 → Segunda a sexta às 08:00"
        ))

    if lower == "lista lembretes" and schema:
        lembretes = listar_lembretes(telefone, schema)
        if not lembretes:
            return AgentResponse(text="📭 Você ainda não possui lembretes cadastrados.")
        resposta = "📋 *Seus lembretes:*\n\n" + "\n".join(
            [f"🔹 {l['id']} - \"{l['mensagem']}\"\n⏰ CRON: `{l['cron']}`\n" for l in lembretes]
        )
        return AgentResponse(text=resposta)

    if lower.startswith("apagar lembrete") and schema:
        if len(partes) >= 3 and partes[2].isdigit():
            sucesso = apagar_lembrete(telefone, int(partes[2]), schema)
            return AgentResponse(text="🗑️ Lembrete apagado com sucesso!" if sucesso else "⚠️ Lembrete não encontrado ou não pertence a você.")
        return AgentResponse(text="❌ Formato inválido. Use: apagar lembrete [ID]")

    if lower.startswith("notícias"):
        return AgentResponse(text=obter_boletim_the_news())

    if lower.startswith("email:"):
        # Mantém compatibilidade sem alterar a regra de negócio; apenas roteia.
        return AgentResponse(text="ℹ️ Fluxo de e-mail mantido no backend atual.")

    if lower.startswith("rota "):
        resultado_rota = calcular_rota(text[5:].strip())
        if isinstance(resultado_rota, dict):
            return AgentResponse(text=resultado_rota.get("erro", "❌ Não foi possível calcular a rota."))
        return AgentResponse(text=str(resultado_rota))

    return AgentResponse(text=(
        "⚠️ Comando não reconhecido.\n"
        "Digite *ajuda* para ver a lista de comandos disponíveis."
    ))


async def _processar_midia(message: IncomingMessage) -> AgentResponse:
    tipo = message.message_type
    caminho = message.metadata.get("local_path")
    if not caminho:
        return AgentResponse(text="⚠️ Mídia recebida, mas o arquivo não foi baixado corretamente.")

    if tipo == "image":
        resultado = try_all_techniques(caminho, message.metadata.get("media_key", "tmp"))
        if not resultado:
            return AgentResponse(text="⚠️ Não consegui extrair nenhuma informação da imagem.")
        if resultado.get("tipo", "").upper() == "QRCODE":
            texto = formatar_qrcode_para_whatsapp(resultado)
        else:
            texto = formatar_codigodebarras_para_whatsapp(resultado)
        return AgentResponse(text=texto, metadata={"parsed": resultado})

    if tipo == "document":
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
        return AgentResponse(text=texto, metadata={"parsed": dados})

    if tipo == "audio":
        return AgentResponse(text="⚠️ Áudio ainda não ativado neste núcleo.")

    return AgentResponse(text="⚠️ Tipo de mídia não suportado.")


async def route_incoming_message(message: IncomingMessage, session: SessionData) -> AgentResponse:
    if message.message_type == "location":
        try:
            latitude, longitude = (message.text or "").split(",", 1)
            salvar_localizacao_usuario(message.user_id, float(latitude), float(longitude))
            return AgentResponse(text="📍 Obrigado por compartilhar sua localização!")
        except Exception:
            return AgentResponse(text="⚠️ Não consegui interpretar sua localização.")

    if message.message_type in {"image", "document", "audio"}:
        return await _processar_midia(message)
    return await _processar_texto_financeiro(message, session)
