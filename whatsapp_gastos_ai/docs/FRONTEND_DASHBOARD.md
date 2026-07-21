# Frontend Web do TCC

Este projeto usa um frontend leve em HTML, CSS e JavaScript puro, servido pelo mesmo FastAPI do backend financeiro.

## O que já foi entregue nesta etapa

- Página de login em `/login`
- Dashboard em `/dashboard`
- Sessão web com cookie HttpOnly
- API de autenticação em `/api/auth/*`
- API do dashboard em `/api/dashboard/*`
- Cartões com saldo, entradas, saídas e faturas pendentes
- Gráficos por categoria e fluxo de caixa
- Lista de movimentações recentes
- Lista de lembretes
- Resumo textual gerado a partir dos dados reais

## Variáveis de ambiente

Configure no Railway ou no `.env`:

- `DATABASE_URL`
- `WEB_JWT_SECRET`
- `WEB_ACCESS_TOKEN_MINUTES`
- `WEB_REFRESH_TOKEN_DAYS`
- `WEB_ADMIN_NAME`
- `WEB_ADMIN_PHONE`
- `WEB_ADMIN_EMAIL`
- `WEB_ADMIN_PASSWORD`
- `WEB_ADMIN_SCHEMA` opcional

## Como acessar

1. Suba o projeto normalmente.
2. Abra `/login`.
3. Entre com o usuário web provisionado pelo backend.
4. Após autenticar, o navegador vai para `/dashboard`.

## Como o acesso funciona

- O login usa `POST /api/auth/login`
- O backend salva sessão em cookie HttpOnly
- O frontend chama `fetch(..., credentials: 'include')`
- As rotas do dashboard só respondem com usuário autenticado

## Estrutura visual

- Identidade em verde financeiro
- Sidebar fixa no desktop
- Layout responsivo para celular
- Componentes separados por arquivo CSS

## Limitações desta etapa

- Ainda não há extrato detalhado por tela
- Ainda não há páginas de metas, relatórios avançados ou conversas
- A etapa atual foca em login, visão geral e leitura real dos dados

## Próximos passos

- Extrato completo
- Gasto por categoria
- Receitas e salários
- Faturas
- Metas
- Conversas
- Configurações
