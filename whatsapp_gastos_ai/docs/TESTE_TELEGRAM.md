# Teste Telegram

## 1. Criar o bot
1. Abra o Telegram e procure `@BotFather`.
2. Envie `/newbot`.
3. Escolha um nome e um `username`.
4. Copie o token gerado.

## 2. Variáveis no Railway
Adicione estas variáveis no serviço:
- `DATABASE_URL`
- `VERIFY_TOKEN`
- `WHATSAPP_TOKEN`
- `PHONE_NUMBER_ID`
- `WHATSAPP_NUMBER`
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `ADMIN_PHONE`

## 3. Como subir
1. Faça deploy no Railway.
2. Se `TELEGRAM_BOT_TOKEN` existir, o Telegram inicia junto com o FastAPI.
3. Se não existir, o FastAPI sobe normalmente e o Telegram fica desativado.

## 4. Como testar
1. Abra o bot no Telegram.
2. Envie `/start`.
3. Envie uma mensagem de texto como `ajuda`.
4. Envie outra mensagem como `total gasto`.
5. Verifique se a sessão é mantida entre mensagens.

## 5. Reset
1. Envie `/reset`.
2. A sessão do Telegram é limpa.
3. Envie uma nova mensagem para iniciar outro fluxo.

## 6. Logs esperados
- `Telegram iniciado`
- `Mensagem texto recebida no Telegram`
- `Sessão resetada`
- `Telegram desativado por falta de token`

## 7. Desativar sem afetar o WhatsApp
Remova apenas `TELEGRAM_BOT_TOKEN`. O WhatsApp continua funcionando pelo webhook.
