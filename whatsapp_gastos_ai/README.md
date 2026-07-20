# WhatsApp Gastos AI

Assistente financeiro multicanal para WhatsApp e Telegram, com backend em FastAPI, PostgreSQL e integrações de automação.

## Visão Geral
- O núcleo do agente é separado dos canais.
- WhatsApp continua como canal oficial.
- Telegram é usado como canal temporário de teste e validação.

## Arquitetura
- `backend/core/`
  - `models.py`: mensagens e respostas padronizadas
  - `sessions.py`: sessões separadas por canal
  - `router.py`: regras e roteamento do agente
  - `agent.py`: ponto único de entrada
- `backend/channels/`
  - `whatsapp_channel.py`: adaptador da Meta
  - `telegram_channel.py`: polling do Telegram

## Inicialização
- Defina as variáveis de ambiente em `.env`
- Se `TELEGRAM_BOT_TOKEN` existir, o Telegram sobe junto com o FastAPI
- Se não existir, o FastAPI sobe normalmente com WhatsApp

## Teste do Telegram
- Consulte `docs/TESTE_TELEGRAM.md`

## Execução
- `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

