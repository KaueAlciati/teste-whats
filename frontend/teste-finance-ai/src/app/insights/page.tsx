"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  Clock3,
  Lightbulb,
  LoaderCircle,
  PiggyBank,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AppLayout } from "@/components/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import {
  api,
  type FinancialProfile,
  type FinancialProfileInput,
  type InsightsAnalysis,
} from "@/lib/api";
import {
  isCompleteProfile,
  onboardingProgress,
  profileToInput,
  resolveInsightsView,
  updateProfileAnswer,
} from "@/lib/insights-flow";


const MONEY = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});
const DATE = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "long",
  year: "numeric",
});
const DATE_TIME = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});
const CHART_COLORS = [
  "#1BAF80",
  "#7562EF",
  "#F59E0B",
  "#EF4A5F",
  "#3B82F6",
  "#14B8A6",
];

type ProfileKey = keyof FinancialProfileInput;
type StepOption = {
  value: string | boolean;
  title: string;
  description?: string;
};
type OnboardingStep = {
  key: ProfileKey;
  eyebrow: string;
  title: string;
  subtitle: string;
  options: StepOption[];
};

const STEPS: OnboardingStep[] = [
  {
    key: "main_goal",
    eyebrow: "Seu momento",
    title: "Qual é seu principal objetivo financeiro?",
    subtitle:
      "Isso direciona a ordem das recomendações, sem limitar suas escolhas.",
    options: [
      { value: "emergency_reserve", title: "Reserva de emergência" },
      { value: "pay_debts", title: "Quitar dívidas" },
      { value: "purchase_goal", title: "Comprar algo" },
      { value: "organize_finances", title: "Organizar minhas finanças" },
      { value: "invest_future", title: "Investir para o futuro" },
      { value: "grow_wealth", title: "Aumentar patrimônio" },
    ],
  },
  {
    key: "investment_horizon",
    eyebrow: "Horizonte",
    title: "Em quanto tempo você pretende alcançar seus objetivos?",
    subtitle:
      "O prazo ajuda a equilibrar previsibilidade, liquidez e risco.",
    options: [
      { value: "up_to_6_months", title: "Até 6 meses" },
      { value: "up_to_1_year", title: "Até 1 ano" },
      { value: "one_to_three_years", title: "1–3 anos" },
      { value: "three_to_five_years", title: "3–5 anos" },
      { value: "more_than_five_years", title: "Mais de 5 anos" },
    ],
  },
  {
    key: "risk_profile",
    eyebrow: "Preferência declarada",
    title: "Como você se sente em relação a risco?",
    subtitle:
      "Esta resposta personaliza o TCC e não substitui uma análise profissional de suitability.",
    options: [
      {
        value: "conservative",
        title: "Conservador",
        description: "Prefiro estabilidade e previsibilidade.",
      },
      {
        value: "moderate",
        title: "Moderado",
        description: "Aceito algumas oscilações por oportunidades melhores.",
      },
      {
        value: "aggressive",
        title: "Arrojado",
        description: "Aceito oscilações maiores pensando no longo prazo.",
      },
    ],
  },
  {
    key: "liquidity_need",
    eyebrow: "Disponibilidade",
    title: "Você precisa ter acesso rápido ao dinheiro?",
    subtitle:
      "Liquidez é a facilidade de transformar uma opção financeira em dinheiro disponível.",
    options: [
      { value: "high", title: "Sim, preciso de alta liquidez" },
      {
        value: "medium",
        title: "Posso deixar parte do dinheiro investida",
      },
      { value: "low", title: "Posso deixar por períodos maiores" },
    ],
  },
  {
    key: "has_debts",
    eyebrow: "Compromissos",
    title: "Hoje você possui dívidas?",
    subtitle:
      "Não pediremos valores; essa informação apenas ajusta a priorização.",
    options: [
      { value: true, title: "Sim" },
      { value: false, title: "Não" },
    ],
  },
  {
    key: "income_type",
    eyebrow: "Previsibilidade",
    title: "Sua renda normalmente é...",
    subtitle: "Isso ajuda a calibrar sugestões de orçamento e reserva.",
    options: [
      { value: "fixed", title: "Fixa" },
      { value: "variable", title: "Variável" },
      { value: "mixed", title: "Misturada" },
    ],
  },
  {
    key: "main_priority",
    eyebrow: "Foco do FinControl AI",
    title: "Em que você mais quer ajuda agora?",
    subtitle:
      "Você poderá atualizar essas respostas quando seu momento mudar.",
    options: [
      { value: "reduce_expenses", title: "Reduzir gastos" },
      { value: "organize_budget", title: "Organizar orçamento" },
      { value: "achieve_goals", title: "Alcançar metas" },
      { value: "start_investing", title: "Começar a investir" },
      { value: "increase_savings", title: "Poupar mais" },
    ],
  },
];


export default function InsightsPage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<FinancialProfile | null>(null);
  const [analysis, setAnalysis] = useState<InsightsAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileLoadFailed, setProfileLoadFailed] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  const loadAnalysis = useCallback(async (force = false) => {
    const result = force
      ? await api.refreshInsightsAnalysis()
      : await api.getInsightsAnalysis();
    setAnalysis(result);
    return result;
  }, []);

  const loadPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProfileLoadFailed(false);
    try {
      const state = await api.getFinancialProfile();
      setProfile(state.profile);
      if (state.onboarding_completed && state.profile) {
        await loadAnalysis();
      }
    } catch {
      setError("Não foi possível carregar seu perfil financeiro agora.");
      setProfileLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [loadAnalysis]);

  useEffect(() => {
    loadPage();
  }, [loadPage]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await loadAnalysis(true);
    } catch {
      setError(
        "Seus dados continuam seguros, mas não foi possível atualizar a análise agora.",
      );
    } finally {
      setRefreshing(false);
    }
  };

  const saveProfile = async (answers: FinancialProfileInput) => {
    setTransitioning(true);
    setError(null);
    let saved: FinancialProfile;
    try {
      saved = profile
        ? await api.updateFinancialProfile(answers)
        : await api.createFinancialProfile(answers);
    } catch {
      setError(
        "Não foi possível salvar seu perfil. Revise as respostas e tente novamente.",
      );
      setTransitioning(false);
      throw new Error("profile-save-failed");
    }
    setProfile(saved);
    setEditingProfile(false);
    try {
      await loadAnalysis(true);
    } catch {
      setError(
        "Seu perfil foi salvo, mas não foi possível carregar a análise agora.",
      );
    }
    setTransitioning(false);
  };

  const analysisLoadFailed = Boolean(profile && !analysis && error && !transitioning);
  const view = resolveInsightsView({
    loading,
    fatalError: profileLoadFailed || analysisLoadFailed,
    hasProfile: Boolean(profile),
    editingProfile,
    transitioning,
    hasAnalysis: Boolean(analysis),
  });

  if (view === "loading") return <InsightsLoading />;

  if (view === "error") {
    return (
      <AppLayout>
        <CenteredState
          icon={<AlertCircle className="text-rose-400" size={36} />}
          title="Não conseguimos abrir seus insights"
          description={error || "Tente novamente em instantes."}
          actionLabel="Tentar novamente"
          onAction={loadPage}
        />
      </AppLayout>
    );
  }

  if (view === "onboarding") {
    return (
      <AppLayout>
        <Onboarding
          profile={profile}
          saving={transitioning}
          error={error}
          onCancel={profile ? () => setEditingProfile(false) : undefined}
          onComplete={saveProfile}
        />
      </AppLayout>
    );
  }

  if (view === "preparing" || !analysis) {
    return (
      <AppLayout>
        <CenteredState
          icon={
            <LoaderCircle
              className="text-emerald-400 animate-spin"
              size={38}
            />
          }
          title="Preparando sua análise financeira..."
          description="Estamos cruzando suas movimentações, categorias e metas sem inventar valores."
        />
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <main className="space-y-8 pb-8">
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
              <BrainCircuit size={18} /> Análise financeira personalizada
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold">
              Olá, {user?.name?.split(" ")[0] || "você"}. Aqui está sua
              análise financeira.
            </h1>
            <p className="text-zinc-500 text-sm">
              Atualizada em {DATE.format(new Date(analysis.generated_at))}.
              Valores calculados pelo backend.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setEditingProfile(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600 hover:bg-zinc-900"
            >
              <Settings2 size={16} /> Atualizar perfil financeiro
            </button>
            <button
              onClick={refresh}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              <RefreshCw
                size={16}
                className={refreshing ? "animate-spin" : ""}
              />
              Atualizar análise
            </button>
          </div>
        </header>

        {error && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
            {error}
          </div>
        )}

        <HealthCard analysis={analysis} />

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Saldo atual"
            value={MONEY.format(analysis.summary.balance)}
            icon={<WalletCards size={19} />}
          />
          <MetricCard
            label="Entradas do mês"
            value={MONEY.format(analysis.summary.current_month_income)}
            icon={<TrendingUp size={19} />}
            positive
          />
          <MetricCard
            label="Despesas do mês"
            value={MONEY.format(analysis.summary.current_month_expenses)}
            icon={<TrendingDown size={19} />}
            negative
          />
          <MetricCard
            label="Valor livre"
            value={MONEY.format(analysis.summary.free_amount)}
            icon={<PiggyBank size={19} />}
            positive={analysis.summary.free_amount >= 0}
            negative={analysis.summary.free_amount < 0}
          />
        </section>

        {analysis.summary.transaction_count === 0 && (
          <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
            <h2 className="font-semibold">Sua estrutura está pronta</h2>
            <p className="mt-2 text-sm text-zinc-400">
              Ainda não existem movimentações para comparar. Registre receitas
              e despesas; os cards serão preenchidos automaticamente sem
              estimativas fictícias.
            </p>
          </section>
        )}

        <ChartsSection analysis={analysis} />

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <InsightList
            title="Pontos positivos"
            icon={<CheckCircle2 className="text-emerald-400" size={19} />}
            items={
              analysis.ai.content?.positive_points ||
              analysis.alerts
                .filter((item) => item.severity === "positive")
                .map((item) => item.message)
            }
            empty="Os dados ainda não sustentam um ponto positivo específico."
          />
          <InsightList
            title="Pontos de atenção"
            icon={<AlertCircle className="text-amber-400" size={19} />}
            items={
              analysis.ai.content?.attention_points ||
              analysis.alerts
                .filter((item) =>
                  ["attention", "critical"].includes(item.severity),
                )
                .map((item) => item.message)
            }
            empty="Nenhum alerta determinístico relevante neste momento."
          />
        </section>

        <AISection analysis={analysis} />
        <GoalsSection analysis={analysis} />
        <ActionsAndPossibilities analysis={analysis} />

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <SectionTitle icon={<Clock3 size={19} />} title="Mercado atual" />
          <p className="mt-3 text-sm text-zinc-400">{analysis.market.message}</p>

          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MarketRateCard label="Selic" indicator={analysis.market.selic} />
            <MarketRateCard label="CDI / Taxa DI" indicator={analysis.market.cdi} />
            <MarketRateCard label="IPCA 12 meses" indicator={analysis.market.ipca} />
            <MarketRateCard label="Poupança" indicator={analysis.market.savings} />
          </div>

          <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Tesouro Selic
                </p>
                {analysis.market.treasury_selic.status === "available" ? (
                  <>
                    <p className="mt-1 text-base font-semibold text-zinc-100">
                      {analysis.market.treasury_selic.title} · vencimento{" "}
                      {analysis.market.treasury_selic.maturity_date
                        ? DATE.format(
                            new Date(
                              `${analysis.market.treasury_selic.maturity_date}T12:00:00`,
                            ),
                          )
                        : "não informado"}
                    </p>
                    <p className="mt-1 text-xl font-bold text-emerald-400">
                      {formatRate(analysis.market.treasury_selic.rate)}{" "}
                      {analysis.market.treasury_selic.unit}
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-sm text-amber-300">Indisponível</p>
                )}
              </div>
              <MarketSourceLink source={analysis.market.treasury_selic.source} />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              {analysis.market.treasury_selic.message ||
                `Referência: ${analysis.market.treasury_selic.reference_period || "não informada"}`}
            </p>
          </div>

          <p className="mt-4 text-xs text-zinc-500">
            Atualizado em{" "}
            {analysis.market.updated_at
              ? DATE_TIME.format(new Date(analysis.market.updated_at))
              : "data indisponível"}
            {analysis.market.cached ? " · dados em cache" : ""}. Indicadores
            indisponíveis não são estimados pela IA.
          </p>
        </section>
      </main>
    </AppLayout>
  );
}


function MarketRateCard({
  label,
  indicator,
}: {
  label: string;
  indicator: InsightsAnalysis["market"]["selic"];
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      {indicator.status === "available" ? (
        <p className="mt-2 text-xl font-bold text-emerald-400">
          {formatRate(indicator.value)} {indicator.unit}
        </p>
      ) : (
        <p className="mt-2 text-sm font-medium text-amber-300">Indisponível</p>
      )}
      <p className="mt-2 min-h-8 text-xs text-zinc-500">
        {indicator.message ||
          `Referência: ${indicator.reference_period || "não informada"}`}
      </p>
      <div className="mt-3">
        <MarketSourceLink source={indicator.source} />
      </div>
    </div>
  );
}

function MarketSourceLink({
  source,
}: {
  source: InsightsAnalysis["market"]["selic"]["source"];
}) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noreferrer"
      className="text-xs text-emerald-400 transition hover:text-emerald-300"
    >
      Fonte: {source.name}
    </a>
  );
}

function formatRate(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}


function Onboarding({
  profile,
  saving,
  error,
  onCancel,
  onComplete,
}: {
  profile: FinancialProfile | null;
  saving: boolean;
  error: string | null;
  onCancel?: () => void;
  onComplete: (answers: FinancialProfileInput) => Promise<void>;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Partial<FinancialProfileInput>>(
    profile ? profileToInput(profile) : {},
  );
  const step = STEPS[stepIndex];
  const selected = answers[step.key];
  const progress = onboardingProgress(stepIndex, STEPS.length);

  const finish = async () => {
    if (!isCompleteProfile(answers)) return;
    try {
      await onComplete(answers);
    } catch {
      // O erro já é exibido pelo componente pai e as respostas são preservadas.
    }
  };

  return (
    <main className="mx-auto max-w-4xl py-2 sm:py-8">
      <div className="mb-8 flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
            <BrainCircuit size={18} /> Perfil financeiro
          </div>
          <h1 className="mt-2 text-2xl sm:text-3xl font-bold">
            {profile
              ? "Atualize sua análise"
              : "Vamos conhecer seu momento financeiro"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-400">
            Sete respostas rápidas para tornar os insights úteis desde o
            primeiro acesso.
          </p>
        </div>
        {onCancel && (
          <button
            onClick={onCancel}
            className="text-sm text-zinc-400 hover:text-white"
          >
            Cancelar
          </button>
        )}
      </div>

      <div className="mb-8">
        <div className="mb-2 flex justify-between text-xs text-zinc-500">
          <span>
            Etapa {stepIndex + 1} de {STEPS.length}
          </span>
          <span>{Math.round(progress)}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <section className="rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 to-zinc-950 p-5 sm:p-8 shadow-2xl shadow-black/20">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-400">
          {step.eyebrow}
        </p>
        <h2 className="mt-3 text-xl sm:text-2xl font-bold">{step.title}</h2>
        <p className="mt-2 text-sm text-zinc-400">{step.subtitle}</p>

        <div className="mt-7 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {step.options.map((option) => {
            const active = selected === option.value;
            return (
              <button
                key={String(option.value)}
                onClick={() =>
                  setAnswers((current) =>
                    updateProfileAnswer(current, step.key, option.value),
                  )
                }
                className={`group min-h-20 rounded-xl border p-4 text-left transition-all ${
                  active
                    ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500/30"
                    : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p
                      className={
                        active
                          ? "font-semibold text-emerald-300"
                          : "font-semibold text-zinc-200"
                      }
                    >
                      {option.title}
                    </p>
                    {option.description && (
                      <p className="mt-1 text-xs leading-relaxed text-zinc-500">
                        {option.description}
                      </p>
                    )}
                  </div>
                  <span
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                      active
                        ? "border-emerald-400 bg-emerald-500 text-white"
                        : "border-zinc-700"
                    }`}
                  >
                    {active && <Check size={13} />}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        {error && (
          <p className="mt-5 rounded-lg border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </p>
        )}

        <div className="mt-8 flex items-center justify-between">
          <button
            onClick={() => setStepIndex((current) => Math.max(0, current - 1))}
            disabled={stepIndex === 0 || saving}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-white disabled:opacity-30"
          >
            <ArrowLeft size={16} /> Voltar
          </button>
          {stepIndex < STEPS.length - 1 ? (
            <button
              onClick={() =>
                setStepIndex((current) =>
                  Math.min(STEPS.length - 1, current + 1),
                )
              }
              disabled={selected === undefined || saving}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              Continuar <ArrowRight size={16} />
            </button>
          ) : (
            <button
              onClick={finish}
              disabled={!isCompleteProfile(answers) || saving}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-40"
            >
              {saving ? (
                <LoaderCircle size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              Finalizar análise
            </button>
          )}
        </div>
      </section>
    </main>
  );
}


function ChartsSection({ analysis }: { analysis: InsightsAnalysis }) {
  return (
    <section className="grid grid-cols-1 gap-6 xl:grid-cols-5">
      <div className="xl:col-span-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
        <SectionTitle icon={<TrendingUp size={18} />} title="Evolução mensal" />
        <div className="mt-5 h-72">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={analysis.summary.monthly_history}>
              <defs>
                <linearGradient id="incomeInsights" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1BAF80" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#1BAF80" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="expenseInsights" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#EF4A5F" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#EF4A5F" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#20302a" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="month" stroke="#718078" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#718078" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(value) => `R$ ${value}`} />
              <Tooltip contentStyle={{ background: "#0e1713", border: "1px solid #26372f", borderRadius: 10 }} formatter={(value: number) => MONEY.format(value)} />
              <Area type="monotone" dataKey="income" name="Entradas" stroke="#1BAF80" fill="url(#incomeInsights)" strokeWidth={2} />
              <Area type="monotone" dataKey="expense" name="Despesas" stroke="#EF4A5F" fill="url(#expenseInsights)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="xl:col-span-2 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
        <SectionTitle icon={<WalletCards size={18} />} title="Comportamento dos gastos" />
        {analysis.summary.category_distribution.length ? (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 items-center gap-2">
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={analysis.summary.category_distribution} dataKey="amount" nameKey="category" innerRadius={45} outerRadius={76} paddingAngle={3}>
                    {analysis.summary.category_distribution.map((item, index) => (
                      <Cell key={item.category} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#0e1713", border: "1px solid #26372f", borderRadius: 10 }} formatter={(value: number) => MONEY.format(value)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              {analysis.summary.category_distribution.slice(0, 5).map((item, index) => (
                <div key={item.category} className="flex items-center justify-between gap-3 text-xs">
                  <span className="flex items-center gap-2 min-w-0 text-zinc-300">
                    <span className="h-2 w-2 rounded-full shrink-0" style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} />
                    <span className="truncate">{item.category}</span>
                  </span>
                  <span className="font-figures text-zinc-500">{item.percentage.toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <EmptyInline text="Sem despesas no mês para distribuir por categoria." />
        )}
      </div>
    </section>
  );
}


function AISection({ analysis }: { analysis: InsightsAnalysis }) {
  return (
    <section className="rounded-xl border border-ai-500/25 bg-ai-500/[0.07] p-6 relative overflow-hidden">
      <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-ai-500/10 blur-3xl" />
      <div className="relative">
        <SectionTitle icon={<Sparkles className="text-ai-400" size={19} />} title="Leitura da IA" />
        {analysis.ai.content ? (
          <div className="mt-4 space-y-5">
            <p className="text-zinc-200 leading-relaxed">{analysis.ai.content.financial_summary}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <TextPanel title="O que pode melhorar" items={analysis.ai.content.improvements} />
              <TextPanel title="Possíveis cortes" items={analysis.ai.content.cut_suggestions} />
            </div>
            <div className="rounded-lg border border-ai-500/20 bg-black/10 p-4">
              <p className="text-xs uppercase tracking-wider text-ai-300 font-bold">Prioridade sugerida</p>
              <p className="mt-2 text-sm text-zinc-300">{analysis.ai.content.prioritization}</p>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            {analysis.ai.message || "A IA está indisponível, mas todos os cálculos desta página continuam válidos."}
          </div>
        )}
        {analysis.ai.cached && <p className="mt-3 text-xs text-zinc-500">Análise da IA reutilizada do cache para reduzir custo.</p>}
      </div>
    </section>
  );
}


function GoalsSection({ analysis }: { analysis: InsightsAnalysis }) {
  return (
    <section className="space-y-4">
      <SectionTitle icon={<Target size={19} />} title="Metas" />
      {analysis.summary.goals.length ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {analysis.summary.goals.map((goal) => (
            <div key={goal.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold">{goal.name}</h3>
                  <p className="mt-1 text-xs text-zinc-500">
                    {goal.target_date ? `Prazo: ${DATE.format(new Date(`${goal.target_date}T12:00:00`))}` : "Sem prazo definido"}
                  </p>
                </div>
                <span className="font-figures text-sm font-bold text-emerald-400">{goal.progress_percentage.toFixed(0)}%</span>
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-800">
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(goal.progress_percentage, 100)}%` }} />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                <GoalStat label="Guardado" value={MONEY.format(goal.current_amount)} />
                <GoalStat label="Objetivo" value={MONEY.format(goal.target_amount)} />
                <GoalStat label="Falta" value={MONEY.format(goal.remaining_amount)} />
              </div>
              {goal.required_monthly_amount !== null && (
                <p className="mt-4 rounded-lg bg-zinc-950/40 p-3 text-xs text-zinc-400">
                  Ritmo necessário até o prazo: aproximadamente <strong className="text-zinc-200">{MONEY.format(goal.required_monthly_amount)}/mês</strong>.
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <EmptyInline text="Você ainda não possui metas ativas. A análise continua disponível com seus demais dados." />
      )}
    </section>
  );
}


function ActionsAndPossibilities({ analysis }: { analysis: InsightsAnalysis }) {
  return (
    <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <SectionTitle icon={<Target size={19} />} title="Plano de ação" />
        <ol className="mt-5 space-y-3">
          {(analysis.ai.content?.next_steps || ["Mantenha seus registros atualizados."]).map((step, index) => (
            <li key={`${index}-${step}`} className="flex gap-3 text-sm text-zinc-300">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-xs font-bold text-emerald-400">{index + 1}</span>
              <span className="pt-0.5">{step}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <SectionTitle icon={<Lightbulb size={19} />} title="Possibilidades para seu dinheiro" />
        <div className="mt-5 space-y-4">
          {analysis.possibilities.map((item) => (
            <div key={item.title} className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-4">
              <h3 className="font-semibold text-zinc-100">{item.title}</h3>
              <p className="mt-1 text-sm text-zinc-400">{item.objective}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-zinc-400">
                <span className="rounded-full bg-zinc-800 px-2 py-1">Prazo: {item.horizon}</span>
                <span className="rounded-full bg-zinc-800 px-2 py-1">Liquidez: {item.liquidity}</span>
                <span className="rounded-full bg-zinc-800 px-2 py-1">Risco: {item.risk}</span>
              </div>
              <p className="mt-3 text-xs text-zinc-500">Cuidado: {item.care}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


function InsightsLoading() {
  return (
    <AppLayout>
      <main className="space-y-6 animate-pulse">
        <div className="h-9 w-2/3 max-w-xl rounded bg-zinc-800" />
        <div className="h-28 rounded-xl bg-zinc-900" />
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="h-28 rounded-xl bg-zinc-900" />
          ))}
        </div>
        <div className="h-80 rounded-xl bg-zinc-900" />
      </main>
    </AppLayout>
  );
}


function HealthCard({ analysis }: { analysis: InsightsAnalysis }) {
  const presentation = {
    good: { label: "Boa", color: "text-emerald-300", border: "border-emerald-500/30", bg: "bg-emerald-500/10" },
    attention: { label: "Atenção", color: "text-amber-300", border: "border-amber-500/30", bg: "bg-amber-500/10" },
    critical: { label: "Crítica", color: "text-rose-300", border: "border-rose-500/30", bg: "bg-rose-500/10" },
  }[analysis.health.level];
  return (
    <section className={`rounded-xl border ${presentation.border} ${presentation.bg} p-5 sm:p-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between`}>
      <div className="flex items-start gap-4">
        <div className={`rounded-lg p-2.5 ${presentation.bg} ${presentation.color}`}><ShieldCheck size={24} /></div>
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500 font-bold">Saúde financeira</p>
          <h2 className={`mt-1 text-2xl font-bold ${presentation.color}`}>{presentation.label}</h2>
          <p className="mt-1 text-sm text-zinc-300">{analysis.health.explanation}</p>
        </div>
      </div>
      <div className="sm:text-right">
        <p className="font-figures text-3xl font-bold">{analysis.health.score}<span className="text-sm text-zinc-500">/100</span></p>
        <p className="text-xs text-zinc-500">regra transparente do sistema</p>
      </div>
    </section>
  );
}


function MetricCard({ label, value, icon, positive, negative }: { label: string; value: string; icon: React.ReactNode; positive?: boolean; negative?: boolean }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5"><div className="flex items-center justify-between text-sm text-zinc-400"><span>{label}</span><span className="rounded-md bg-zinc-800 p-1.5">{icon}</span></div><p className={`mt-3 font-figures text-2xl font-bold ${positive ? "text-emerald-400" : negative ? "text-rose-400" : "text-zinc-50"}`}>{value}</p></div>;
}

function InsightList({ title, icon, items, empty }: { title: string; icon: React.ReactNode; items: string[]; empty: string }) {
  return <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"><SectionTitle icon={icon} title={title} /><div className="mt-4 space-y-3">{items.length ? items.slice(0, 5).map((item, index) => <div key={`${index}-${item}`} className="flex gap-3 text-sm text-zinc-300"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" /><span>{item}</span></div>) : <p className="text-sm text-zinc-500">{empty}</p>}</div></section>;
}

function TextPanel({ title, items }: { title: string; items: string[] }) {
  return <div className="rounded-lg border border-ai-500/15 bg-black/10 p-4"><h3 className="text-sm font-semibold text-ai-300">{title}</h3><ul className="mt-3 space-y-2 text-sm text-zinc-300">{items.length ? items.map((item) => <li key={item} className="flex gap-2"><span className="text-ai-400">•</span>{item}</li>) : <li className="text-zinc-500">Sem sugestão com os dados atuais.</li>}</ul></div>;
}

function GoalStat({ label, value }: { label: string; value: string }) {
  return <div><p className="text-zinc-600">{label}</p><p className="mt-1 font-figures text-zinc-300 truncate">{value}</p></div>;
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <h2 className="flex items-center gap-2 font-semibold text-zinc-200"><span className="text-emerald-400">{icon}</span>{title}</h2>;
}

function EmptyInline({ text }: { text: string }) {
  return <div className="mt-5 rounded-lg border border-dashed border-zinc-800 p-5 text-center text-sm text-zinc-500">{text}</div>;
}

function CenteredState({ icon, title, description, actionLabel, onAction }: { icon: React.ReactNode; title: string; description: string; actionLabel?: string; onAction?: () => void }) {
  return <main className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center"><div className="rounded-xl bg-zinc-900 p-3">{icon}</div><h1 className="mt-4 text-xl font-bold">{title}</h1><p className="mt-2 max-w-lg text-sm text-zinc-400">{description}</p>{actionLabel && onAction && <button onClick={onAction} className="mt-5 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold hover:bg-emerald-500">{actionLabel}</button>}</main>;
}
