# Cadastro e Vinculação

Este projeto usa uma conta web única para concentrar o painel, o Telegram e, em etapas futuras, o WhatsApp.

## 1. Como criar conta

1. Acesse `/register`
2. Preencha nome, e-mail, telefone e senha
3. Aceite os termos
4. Confirme o cadastro

## 2. Como fazer login

1. Acesse `/login`
2. Entre com e-mail ou telefone normalizado
3. Digite a senha
4. O backend cria a sessão com cookie HttpOnly

## 3. Como vincular Telegram

1. Faça login no painel
2. Abra `/configuracoes`
3. Clique em `Vincular Telegram`
4. O backend gera um código temporário de 6 dígitos
5. Abra o bot no Telegram e envie:
   `/vincular 123456`
6. O bot confirma o vínculo e associa `telegram:{id}` ao usuário interno

## 4. Como desvincular

Na página `/configuracoes`, use o botão de desvincular Telegram.

## 5. Como funciona o user_id interno

- O canal recebe um identificador próprio, como `telegram:123456789`
- O backend procura esse vínculo em `user_channels`
- Depois da validação, o agente recebe o `user_id` interno do banco
- Isso permite que o mesmo usuário use web, Telegram e WhatsApp com os mesmos dados

## 6. Como os canais compartilham dados

- O painel web grava tudo usando o `user_id` interno
- O Telegram, após o vínculo, grava no mesmo usuário interno
- O histórico de conversas também usa `user_id` interno + canal

## 7. Segurança

- Senhas são armazenadas com hash forte
- Códigos de vinculação expiram
- O token de vínculo não é salvo em texto puro
- A sessão web usa cookie HttpOnly
- O acesso ao Telegram é bloqueado quando não existe vínculo

## 8. Migrar usuários antigos

- Os usuários antigos são preservados
- Os campos novos são preenchidos por migração idempotente
- O schema financeiro existente não é apagado

## 9. Como testar localmente

1. Configure `DATABASE_URL`
2. Configure `WEB_JWT_SECRET`
3. Configure `WEB_ADMIN_*` se quiser criar um admin inicial
4. Rode o backend
5. Abra `/register`
6. Faça login
7. Gere um código em `/configuracoes`
8. Envie `/vincular CODIGO` no Telegram

## 10. Como testar no Railway

1. Suba as variáveis de ambiente
2. Faça deploy
3. Abra `/register`
4. Faça login
5. Gere o código de Telegram
6. Teste o vínculo pelo bot

## 11. Variáveis necessárias

- `DATABASE_URL`
- `WEB_JWT_SECRET`
- `WEB_ACCESS_TOKEN_MINUTES`
- `WEB_REFRESH_TOKEN_DAYS`
- `WEB_ADMIN_NAME`
- `WEB_ADMIN_PHONE`
- `WEB_ADMIN_EMAIL`
- `WEB_ADMIN_PASSWORD`
- `APP_ENV`

## 12. Observação sobre WhatsApp

Nesta etapa o vínculo seguro foi implementado para Telegram. O WhatsApp continua com a arquitetura preparada para a próxima fase.
