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

## Interface Web do TCC
- Frontend em HTML/CSS/JS puro, servido pelo mesmo FastAPI
- Login com cookie HttpOnly e dashboard com dados reais do PostgreSQL
- Cadastro web com e-mail, telefone e senha
- Página de configurações para vínculo do Telegram
- Rotas principais:
  - `/login`
  - `/register`
  - `/dashboard`
  - `/configuracoes`
  - `/api/auth/me`
  - `/api/auth/register`
  - `/api/auth/request-email-verification`
  - `/api/auth/verify-email`
  - `/api/dashboard/summary`
  - `/api/dashboard/categories`
  - `/api/dashboard/cash-flow`
  - `/api/dashboard/recent-transactions`
  - `/api/integrations/telegram/status`
  - `/api/integrations/telegram/code`
  - `/api/integrations/telegram`
- Variáveis principais:
  - `WEB_JWT_SECRET`
  - `WEB_ADMIN_PHONE`
  - `WEB_ADMIN_EMAIL`
  - `WEB_ADMIN_PASSWORD`
  - `WEB_ADMIN_NAME`
  - `WEB_ACCESS_TOKEN_MINUTES`
  - `WEB_REFRESH_TOKEN_DAYS`
- O Telegram e o WhatsApp continuam funcionando no mesmo backend; a web é apenas mais um canal de visualização e gestão.

## Execução
- `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
