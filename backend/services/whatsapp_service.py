import logging
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
WHATSAPP_BOT_URL = os.getenv("WHATSAPP_BOT_URL")
TOKEN = os.getenv("TOKEN")
PHONE_ID = os.getenv("PHONE_ID")

logger = logging.getLogger(__name__)

async def enviar_mensagem_whatsapp(telefone, mensagem):
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": mensagem}
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("✅ Mensagem enviada com sucesso para %s", telefone)
            return True
    except httpx.HTTPStatusError as exc:
        logger.error("❌ Erro ao enviar mensagem: %s", exc.response.text)
        return False
    except Exception as e:
        logger.exception("❌ Erro inesperado ao enviar mensagem:")
        return False


async def enviar_menu_interativo(telefone, titulo, opcoes):
    """
    Envia um menu interativo com botões
    
    Args:
        telefone: número do destinatário
        titulo: título do menu
        opcoes: lista de dicts com 'id' e 'title' (max 3 opções)
    """
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Monta os botões (máximo 3)
    buttons = [
        {"type": "reply", "reply": {"id": op["id"], "title": op["title"]}}
        for op in opcoes[:3]
    ]
    
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": titulo},
            "action": {"buttons": buttons}
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("✅ Menu interativo enviado para %s", telefone)
            return True
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar menu interativo:")
        return False


async def enviar_lista_interativa(telefone, titulo, corpo, nome_botao, secoes):
    """
    Envia uma lista interativa (para mais de 3 opções)
    
    Args:
        telefone: número
        titulo: título da mensagem
        corpo: texto do corpo
        nome_botao: texto do botão (ex: "Ver opções")
        secoes: lista de seções, cada uma com título e rows
        
    Exemplo:
        secoes = [
            {
                "title": "Produtos",
                "rows": [
                    {"id": "banner", "title": "Banner"},
                    {"id": "cartao", "title": "Cartão de visita"}
                ]
            }
        ]
    """
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": titulo},
            "body": {"text": corpo},
            "action": {
                "button": nome_botao,
                "sections": secoes
            }
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info("✅ Lista interativa enviada para %s", telefone)
            return True
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar lista interativa:")
        return False


async def obter_url_midia(media_id: str) -> str:
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            media_info = response.json()
            return media_info.get("url")
    except Exception as e:
        logger.exception(f"❌ Erro ao obter URL da mídia com ID {media_id}:")
        return None


async def baixar_midia(url: str, caminho_destino: str):
    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            with open(caminho_destino, "wb") as f:
                f.write(response.content)
        logger.info(f"✅ Mídia salva em {caminho_destino}")
    except Exception as e:
        logger.exception(f"❌ Erro ao baixar a mídia da URL {url}:")


async def enviar_imagem_whatsapp(telefone, caminho_imagem, caption=None):
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        upload_url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/media"
        
        with open(caminho_imagem, "rb") as image_file:
            files = {
                'file': (os.path.basename(caminho_imagem), image_file, 'image/png')
            }
            form_data = {
                'messaging_product': 'whatsapp',
                'type': 'image/png'
            }
            
            async with httpx.AsyncClient() as client:
                upload_response = await client.post(
                    upload_url,
                    headers={"Authorization": f"Bearer {TOKEN}"},
                    files=files,
                    data=form_data
                )
                
                if upload_response.status_code != 200:
                    logger.error(f"Erro ao fazer upload da imagem: {upload_response.text}")
                    return False
                
                media_id = upload_response.json().get('id')
                
                if not media_id:
                    logger.error("Não foi possível obter o media_id após upload")
                    return False
                
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone,
                    "type": "image",
                    "image": {
                        "id": media_id,
                        "caption": caption if caption else None
                    }
                }
                
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    logger.error(f"Erro ao enviar imagem: {response.text}")
                    return False
                
                logger.info("✅ Imagem enviada com sucesso para %s", telefone)
                return True
                
    except Exception as e:
        logger.exception(f"❌ Erro ao enviar imagem: {e}")
        await enviar_mensagem_whatsapp(
            telefone, 
            "❌ Desculpe, não foi possível enviar a imagem do comprovante. Erro técnico."
        )
        return False