import logging
from whatsapp import enviar_mensagem_whatsapp, enviar_lista_interativa
from chatwoot_integration import transferir_para_vendedor

logger = logging.getLogger(__name__)

# Simula um banco de dados de sessões
sessoes = {}

async def verificar_handoff(telefone: str) -> bool:
    """Verifica se conversa já foi transferida para vendedor"""
    return sessoes.get(telefone, {}).get("handoff", False)


async def marcar_handoff(telefone: str):
    """Marca conversa como transferida"""
    if telefone not in sessoes:
        sessoes[telefone] = {}
    sessoes[telefone]["handoff"] = True


async def processar_mensagem_bot(telefone: str, mensagem: str, tipo_mensagem: str = "text"):
    """
    Processa mensagens do bot de gráfica
    
    Args:
        telefone: número do cliente
        mensagem: conteúdo da mensagem
        tipo_mensagem: "text", "interactive", etc.
    """
    
    # ⚠️ IMPORTANTE: Se já foi transferido, ignora
    if await verificar_handoff(telefone):
        logger.info(f"⏭️ Conversa com {telefone} já está com vendedor. Ignorando.")
        return
    
    # Inicializa sessão se não existir
    if telefone not in sessoes:
        sessoes[telefone] = {
            "etapa": "inicio",
            "dados": {}
        }
    
    sessao = sessoes[telefone]
    etapa_atual = sessao["etapa"]
    
    # ========== FLUXO DO BOT ==========
    
    # 1️⃣ INÍCIO - Envia menu de produtos
    if etapa_atual == "inicio":
        await enviar_lista_interativa(
            telefone,
            titulo="Olá! 👋 Bem-vindo à Gráfica XP",
            corpo="Qual produto você precisa?",
            nome_botao="Ver produtos",
            secoes=[
                {
                    "title": "Produtos disponíveis",
                    "rows": [
                        {"id": "cartao", "title": "Cartão de visita", "description": "500un a partir de R$50"},
                        {"id": "banner", "title": "Banner", "description": "Diversos tamanhos"},
                        {"id": "panfleto", "title": "Panfleto/Flyer", "description": "A partir de 1000un"},
                        {"id": "adesivo", "title": "Adesivo", "description": "Personalizados"},
                        {"id": "outro", "title": "Outro produto", "description": "Falar com vendedor"}
                    ]
                }
            ]
        )
        sessao["etapa"] = "aguardando_produto"
    
    # 2️⃣ PRODUTO SELECIONADO
    elif etapa_atual == "aguardando_produto":
        produto = mensagem.lower()
        
        if produto == "outro":
            # Transfere direto para vendedor
            await enviar_mensagem_whatsapp(
                telefone,
                "Sem problemas! Vou te passar para um vendedor agora 😊"
            )
            await transferir_para_vendedor(telefone, {"produto": "outro", "observacao": "Cliente quer produto não listado"})
            await marcar_handoff(telefone)
            return
        
        sessao["dados"]["produto"] = produto
        await enviar_mensagem_whatsapp(
            telefone,
            f"Ótimo! Você escolheu: **{produto.upper()}**\n\nQuantas unidades você precisa?"
        )
        sessao["etapa"] = "aguardando_quantidade"
    
    # 3️⃣ QUANTIDADE
    elif etapa_atual == "aguardando_quantidade":
        try:
            quantidade = int(mensagem.strip())
            sessao["dados"]["quantidade"] = quantidade
            
            await enviar_mensagem_whatsapp(
                telefone,
                f"Perfeito! {quantidade} unidades.\n\nPara quando você precisa? (ex: 5 dias, 1 semana)"
            )
            sessao["etapa"] = "aguardando_prazo"
            
        except ValueError:
            await enviar_mensagem_whatsapp(
                telefone,
                "Por favor, envie apenas o número de unidades (ex: 500)"
            )
    
    # 4️⃣ PRAZO
    elif etapa_atual == "aguardando_prazo":
        prazo = mensagem.strip()
        sessao["dados"]["prazo"] = prazo
        
        await enviar_mensagem_whatsapp(
            telefone,
            "Entendi! Última pergunta:\n\nVocê já tem a arte pronta?\n\n1️⃣ Sim, tenho\n2️⃣ Não, preciso de ajuda"
        )
        sessao["etapa"] = "aguardando_arte"
    
    # 5️⃣ ARTE PRONTA (FINAL)
    elif etapa_atual == "aguardando_arte":
        arte = mensagem.strip()
        
        if arte in ["1", "sim", "tenho"]:
            sessao["dados"]["arte_pronta"] = "Sim"
        else:
            sessao["dados"]["arte_pronta"] = "Não, precisa de ajuda"
        
        # ✅ COLETA COMPLETA - TRANSFERE PARA VENDEDOR
        await enviar_mensagem_whatsapp(
            telefone,
            "Perfeito! 😊\n\nVou te encaminhar para um vendedor que vai passar o orçamento e detalhes.\n\nAguarde um momento..."
        )
        
        # Transfere para Chatwoot
        dados = sessao["dados"]
        conversation_id = await transferir_para_vendedor(telefone, dados)
        
        if conversation_id:
            await marcar_handoff(telefone)
            logger.info(f"✅ Cliente {telefone} transferido com sucesso para Chatwoot (conversa {conversation_id})")
        else:
            await enviar_mensagem_whatsapp(
                telefone,
                "⚠️ Desculpe, tivemos um erro ao conectar com o vendedor. Tente novamente em instantes."
            )


# ========== WEBHOOK HANDLER ==========
async def processar_webhook_whatsapp(webhook_data: dict):
    """
    Processa webhooks recebidos do WhatsApp
    """
    try:
        entry = webhook_data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        messages = value.get("messages", [])
        if not messages:
            return
        
        message = messages[0]
        telefone = message.get("from")
        
        # Tipos de mensagem
        tipo = message.get("type")
        
        if tipo == "text":
            texto = message.get("text", {}).get("body", "")
            await processar_mensagem_bot(telefone, texto, "text")
            
        elif tipo == "interactive":
            # Resposta de botão ou lista
            interactive = message.get("interactive", {})
            
            if interactive.get("type") == "button_reply":
                button_id = interactive.get("button_reply", {}).get("id")
                await processar_mensagem_bot(telefone, button_id, "interactive")
                
            elif interactive.get("type") == "list_reply":
                list_id = interactive.get("list_reply", {}).get("id")
                await processar_mensagem_bot(telefone, list_id, "interactive")
        
        else:
            logger.info(f"Tipo de mensagem não tratado: {tipo}")
            
    except Exception as e:
        logger.exception("❌ Erro ao processar webhook:")