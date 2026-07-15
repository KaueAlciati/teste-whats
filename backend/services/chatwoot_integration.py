import logging
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

CHATWOOT_URL = os.getenv("CHATWOOT_URL")
CHATWOOT_API_KEY = os.getenv("CHATWOOT_API_KEY")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID")  # ID da inbox do WhatsApp

logger = logging.getLogger(__name__)


async def criar_contato_chatwoot(telefone: str, nome: str = None):
    """Cria ou atualiza um contato no Chatwoot"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts"
    headers = {
        "api_access_token": CHATWOOT_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "inbox_id": CHATWOOT_INBOX_ID,
        "phone_number": telefone,
        "name": nome or f"Cliente {telefone[-4:]}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                contact_data = response.json()
                logger.info(f"✅ Contato criado no Chatwoot: {telefone}")
                return contact_data.get("payload", {}).get("contact", {}).get("id")
            else:
                logger.warning(f"⚠️ Contato pode já existir: {response.text}")
                return None
                
    except Exception as e:
        logger.exception(f"❌ Erro ao criar contato no Chatwoot:")
        return None


async def criar_conversa_chatwoot(telefone: str, contact_id: int = None):
    """Cria uma conversa no Chatwoot"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations"
    headers = {
        "api_access_token": CHATWOOT_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Se não tem contact_id, busca ou cria
    if not contact_id:
        contact_id = await buscar_contato_chatwoot(telefone)
        if not contact_id:
            contact_id = await criar_contato_chatwoot(telefone)
    
    payload = {
        "source_id": telefone,
        "inbox_id": CHATWOOT_INBOX_ID,
        "contact_id": contact_id,
        "status": "open"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                conversation_data = response.json()
                conversation_id = conversation_data.get("id")
                logger.info(f"✅ Conversa criada no Chatwoot: {conversation_id}")
                return conversation_id
            else:
                logger.error(f"❌ Erro ao criar conversa: {response.text}")
                return None
                
    except Exception as e:
        logger.exception(f"❌ Erro ao criar conversa no Chatwoot:")
        return None


async def buscar_contato_chatwoot(telefone: str):
    """Busca um contato pelo telefone"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/contacts/search"
    headers = {
        "api_access_token": CHATWOOT_API_KEY
    }
    params = {
        "q": telefone
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                contacts = data.get("payload", [])
                if contacts:
                    return contacts[0].get("id")
            return None
            
    except Exception as e:
        logger.exception(f"❌ Erro ao buscar contato:")
        return None


async def enviar_mensagem_privada_chatwoot(conversation_id: int, mensagem: str):
    """Envia uma mensagem privada (nota interna) para os atendentes"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
    headers = {
        "api_access_token": CHATWOOT_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "content": mensagem,
        "message_type": "outgoing",
        "private": True  # Mensagem privada (só atendentes veem)
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Nota interna enviada na conversa {conversation_id}")
                return True
            else:
                logger.error(f"❌ Erro ao enviar nota: {response.text}")
                return False
                
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar mensagem privada:")
        return False


async def adicionar_label_chatwoot(conversation_id: int, labels: list):
    """Adiciona labels/tags na conversa"""
    url = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/labels"
    headers = {
        "api_access_token": CHATWOOT_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "labels": labels  # Ex: ["bot", "grafica", "banner"]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Labels adicionadas: {labels}")
                return True
            else:
                logger.error(f"❌ Erro ao adicionar labels: {response.text}")
                return False
                
    except Exception as e:
        logger.exception(f"❌ Erro ao adicionar labels:")
        return False


async def transferir_para_vendedor(telefone: str, dados_coletados: dict):
    """
    Transfere o atendimento do bot para um vendedor humano
    
    Args:
        telefone: número do cliente
        dados_coletados: dict com info coletada pelo bot
    """
    
    # 1. Busca ou cria contato
    contact_id = await buscar_contato_chatwoot(telefone)
    if not contact_id:
        contact_id = await criar_contato_chatwoot(telefone)
    
    if not contact_id:
        logger.error("❌ Não foi possível criar contato no Chatwoot")
        return False
    
    # 2. Cria conversa
    conversation_id = await criar_conversa_chatwoot(telefone, contact_id)
    
    if not conversation_id:
        logger.error("❌ Não foi possível criar conversa no Chatwoot")
        return False
    
    # 3. Monta resumo para o vendedor
    resumo = "📌 **Atendimento iniciado pelo bot**\n\n"
    resumo += "**Cliente quer:**\n"
    resumo += f"• Produto: {dados_coletados.get('produto', 'N/A')}\n"
    resumo += f"• Quantidade: {dados_coletados.get('quantidade', 'N/A')}\n"
    resumo += f"• Prazo: {dados_coletados.get('prazo', 'N/A')}\n"
    resumo += f"• Arte pronta: {dados_coletados.get('arte_pronta', 'N/A')}\n\n"
    resumo += "🔔 **Encaminhado para vendedor**"
    
    # 4. Envia resumo como nota interna
    await enviar_mensagem_privada_chatwoot(conversation_id, resumo)
    
    # 5. Adiciona labels
    produto = dados_coletados.get('produto', '').lower()
    await adicionar_label_chatwoot(conversation_id, ["bot", "grafica", produto])
    
    logger.info(f"✅ Conversa {conversation_id} transferida para vendedor")
    
    return conversation_id