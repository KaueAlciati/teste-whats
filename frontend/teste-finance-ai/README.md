# Finance.AI

Controle financeiro pessoal com dashboard, metas, transações e insights gerados a partir do histórico real de cada conta.

Landing pública em `/`, app autenticado a partir de `/dashboard`. Funciona com backend real (FastAPI + SQLite) ou em modo local (`localStorage`) quando o backend está indisponível.

## Stack

**Frontend** — Next.js 15 (App Router) · React 18 · TypeScript · Tailwind CSS · React Query · Recharts · Radix UI

**Backend** — FastAPI · SQLite (via `sqlite3` nativo, sem ORM) · PBKDF2 para senha · sessões por token opaco

## Rodando localmente

### 1. Backend

```bash
cd backend
pip install fastapi uvicorn --break-system-packages   # ou num virtualenv
uvicorn app.main:app --reload
```

Sobe em `http://localhost:8000`. Na primeira execução, o banco `finance.db` é criado automaticamente com uma **conta de demonstração populada**:

```
E-mail: demo@finance.ai
Senha:  demo123456
```

### 2. Frontend

```bash
npm install
npm run dev
```

Sobe em `http://localhost:3000`.

### 3. Os dois juntos

```bash
npm run dev:all
```

## Variáveis de ambiente

| Variável | Onde | Padrão | Descrição |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | frontend | `http://localhost:8000/api` | URL base da API |
| `ALLOWED_ORIGINS` | backend | `http://localhost:3000` | Origens liberadas no CORS (separadas por vírgula) |
| `SECRET_KEY` / `JWT_SECRET` | backend | valor de desenvolvimento | **Trocar obrigatoriamente em produção** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | backend | `60` | Usado no payload informativo de JWT (ver nota em `docs/ARQUITETURA.md`) |
| `DATABASE_URL` | backend | `sqlite:///./finance.db` | Caminho do banco |

## Modo local (sem backend)

Se o backend estiver fora do ar, o frontend detecta automaticamente (`checkBackendAvailability()` em `src/lib/storage.ts`) e passa a usar `localStorage` para tudo — login, transações, metas, notificações. É útil para demonstração offline, mas **os dois modos não sincronizam entre si**: dados criados em modo local não aparecem depois quando o backend voltar, e vice-versa.

## Estrutura

```
backend/
  app/
    core/          → config, conexão com banco, segurança (hash de senha), RBAC
    repositories/   → acesso direto ao SQLite, sempre filtrado por user_id
    services/       → regra de negócio (cada repositório tem um serviço correspondente)
    routers/        → endpoints HTTP, um arquivo por domínio
    schemas/        → modelos Pydantic de request/response
    dependencies.py → identifica o usuário autenticado a partir do token de sessão
    main.py         → monta o app, CORS, registra routers

src/
  app/              → páginas (App Router) — uma pasta por rota
  components/       → componentes de UI compartilhados
  components/ui/    → biblioteca de componentes primitivos (Button, Dialog, Tabs...)
  features/notifications/ → módulo isolado de notificações (hooks, tipos, serviço)
  contexts/         → AuthContext, DataContext, ToastContext
  hooks/            → hooks compartilhados (ex: useHandleFetchError)
  lib/
    api.ts          → chamadas HTTP reais ao backend
    localStorage.ts → implementação equivalente em modo local
    storage.ts       → decide qual das duas usar, com fallback automático
```

## Funcionalidades

- Cadastro, login, logout, recuperação de senha (fluxo de e-mail ainda não implementado — ver `docs/IDEIAS.md`)
- Edição de perfil e troca de senha reais
- Transações: criar, editar, excluir, listar, exportar em CSV (respeitando o filtro de busca aplicado)
- Metas: criar, depositar, concluir, excluir, com percentual de progresso
- Dashboard com saldo, entradas, saídas e tendência mês a mês de cada um (calculados separadamente — antes um bug fazia o card de Entradas mostrar a variação de Saídas por engano)
- Insights gerados a partir do histórico real: categoria de gasto dominante, despesas recorrentes detectadas automaticamente, pressão de fluxo de caixa, tendência de receita, mudança de comportamento por categoria (com explicabilidade: valor atual vs. anterior, diferença e principais responsáveis), resumo financeiro do mês, projeção de tempo até concluir a próxima meta
- Importação de extrato (CSV e OFX pela API; só CSV também funciona no modo LocalStorage)
- Notificações (lista, filtros, marcar como lida/todas como lidas)
- Isolamento real de dados por conta — testado explicitamente com duas contas simultâneas

## Documentação adicional

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — como a autenticação funciona, fluxo de dados, decisões de design
- [`docs/IDEIAS.md`](docs/IDEIAS.md) — próximas implementações sugeridas, por prioridade
- [`docs/SEGURANCA.md`](docs/SEGURANCA.md) — o que já foi corrigido, o que ainda precisa de atenção antes de produção
- [`docs/MELHORIAS.md`](docs/MELHORIAS.md) — mudanças mais recentes (layout mobile, exportar CSV, correção do toggle de IA, Configurações redesenhada) e por que cada uma foi feita
- [`docs/MELHORIAS-CICLOS.md`](docs/MELHORIAS-CICLOS.md) — rodada seguinte: normalização de categoria, Insights com explicabilidade, importação CSV e tendências no modo LocalStorage, redesign de Insights e identidade visual da IA
