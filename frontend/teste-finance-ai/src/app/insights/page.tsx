"use client";

import { useEffect, useState, useCallback } from "react";
import {
  BrainCircuit,
  Sparkles,
  Target,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  TrendingDown,
  Info,
  PiggyBank,
} from "lucide-react";
import Link from "next/link";
import { storage } from "@/lib/storage";
import type { InsightData, InsightEntry } from "@/lib/api";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AppLayout } from "@/components/AppLayout";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";

const formatCurrency = (value: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

export default function InsightsPage() {
  const [data, setData] = useState<InsightData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  // Distinto de "error": ausência de dados não é uma falha do sistema,
  // é só uma conta nova/sem histórico suficiente ainda — antes, os
  // dois casos caíam na mesma tela de "verifique se o backend está
  // online", o que é enganoso pra quem só ainda não usou o app.
  const [insufficientData, setInsufficientData] = useState(false);
  const handleFetchError = useHandleFetchError();

  const loadInsights = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);
      setInsufficientData(false);
      const json = await storage.getInsights();
      if (json) {
        setData(json);
      } else {
        setInsufficientData(true);
      }
    } catch (err) {
      await handleFetchError(err, "Erro ao carregar insights:");
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [handleFetchError]);

  useEffect(() => {
    loadInsights();
  }, [loadInsights]);

  if (error) {
    return (
      <AppLayout>
        <main className="flex flex-col items-center justify-center min-h-[60vh] space-y-4 text-center px-4">
          <div className="p-3 bg-rose-500/10 rounded-xl">
            <AlertCircle size={40} className="text-rose-500" />
          </div>
          <h2 className="text-xl font-bold">Não foi possível carregar seus insights</h2>
          <p className="text-zinc-400">Tente novamente em instantes.</p>
          <button
            onClick={loadInsights}
            className="bg-zinc-800 hover:bg-zinc-700 px-6 py-2 rounded-lg transition-colors text-sm font-medium"
          >
            Tentar novamente
          </button>
        </main>
      </AppLayout>
    );
  }

  if (!loading && insufficientData) {
    return (
      <AppLayout>
        <main className="flex flex-col items-center justify-center min-h-[60vh] space-y-4 text-center px-4">
          <div className="p-3 bg-ai-500/10 rounded-xl">
            <BrainCircuit size={40} className="text-ai-400" />
          </div>
          <h2 className="text-xl font-bold">Ainda não há dados suficientes</h2>
          <p className="text-zinc-400 max-w-sm">
            Ainda precisamos de mais movimentações para identificar padrões financeiros com maior
            precisão. Cadastre algumas transações para liberar as análises.
          </p>
          <Link
            href="/transactions"
            className="bg-emerald-600 hover:bg-emerald-500 px-6 py-2 rounded-lg transition-colors text-sm font-medium"
          >
            Adicionar transação
          </Link>
        </main>
      </AppLayout>
    );
  }

  // Antes, desligar "Insights Semanais da IA" em Configurações não
  // mudava nada nesta tela: o backend continuava tentando gerar as
  // mesmas análises e o usuário via os cards normalmente, sem
  // nenhuma indicação de que o toggle existia. Agora a página inteira
  // reflete o estado desligado, em vez de só o card do Dashboard.
  if (!loading && data?.ai_enabled === false) {
    return (
      <AppLayout>
        <main className="flex flex-col items-center justify-center min-h-[60vh] space-y-4 text-center px-4">
          <div className="p-3 bg-ai-500/10 rounded-xl">
            <BrainCircuit size={40} className="text-ai-400" />
          </div>
          <h2 className="text-xl font-bold">Insights de IA desativados</h2>
          <p className="text-zinc-400 max-w-sm">
            Você desligou os insights automáticos nas suas Configurações. Reative para voltar a
            receber análises sobre seus hábitos financeiros.
          </p>
          <Link
            href="/settings"
            className="bg-emerald-600 hover:bg-emerald-500 px-6 py-2 rounded-lg transition-colors text-sm font-medium"
          >
            Ir para Configurações
          </Link>
        </main>
      </AppLayout>
    );
  }

  // "Principal descoberta" (seção 2 do prompt: "Existe algum
  // comportamento que merece minha atenção?") é o insight de maior
  // severidade — o backend já os devolve nesta prioridade, então só
  // precisamos separar o primeiro do resto, não reordenar nada.
  const [heroInsight, ...restInsights] = data?.insights ?? [];

  return (
    <AppLayout>
      <main className="space-y-8 pb-4">
        {/* Cabeçalho */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-ai-500/10 rounded-lg">
              <BrainCircuit className="w-6 h-6 text-ai-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Insights de IA</h1>
              <p className="text-zinc-500 text-sm flex items-center gap-1.5">
                {!loading && data ? (
                  <>
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" aria-hidden="true" />
                    Análise sincronizada com seus dados
                  </>
                ) : (
                  <>
                    <span
                      className="w-1.5 h-1.5 rounded-full bg-ai-400 shrink-0 animate-ai-pulse"
                      aria-hidden="true"
                    />
                    Analisando seus dados...
                  </>
                )}
              </p>
            </div>
          </div>
        </header>

        {/* Resumo financeiro do mês — "Como está minha vida financeira?" */}
        {data?.resumo_mensal && (
          <section className="p-6 rounded-xl border border-zinc-800 bg-zinc-900/50 space-y-4 animate-fade-slide-up">
            <h2 className="text-lg font-semibold text-zinc-300">
              Resumo de {data.resumo_mensal.month_label}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Receitas</p>
                <p className="text-xl font-bold text-emerald-400 flex items-center gap-1.5 flex-wrap">
                  {formatCurrency(data.resumo_mensal.incomes)}
                  {data.resumo_mensal.income_trend_percentage !== 0 && (
                    <span
                      className={`text-xs font-medium flex items-center gap-0.5 ${
                        data.resumo_mensal.income_trend_percentage > 0 ? "text-emerald-500" : "text-zinc-500"
                      }`}
                    >
                      {data.resumo_mensal.income_trend_percentage > 0 ? (
                        <TrendingUp size={12} />
                      ) : (
                        <TrendingDown size={12} />
                      )}
                      {Math.abs(data.resumo_mensal.income_trend_percentage)}%
                    </span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Despesas</p>
                <p className="text-xl font-bold text-rose-400">{formatCurrency(data.resumo_mensal.expenses)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">Saldo do mês</p>
                <p
                  className={`text-xl font-bold ${data.resumo_mensal.balance >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {formatCurrency(data.resumo_mensal.balance)}
                </p>
              </div>
            </div>
            {data.resumo_mensal.top_categories.length > 0 && (
              <div className="pt-4 border-t border-zinc-800/50 space-y-2">
                <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-wider">
                  Onde você mais gastou
                </p>
                <div className="space-y-1.5">
                  {data.resumo_mensal.top_categories.map((cat) => (
                    <div key={cat.category} className="flex items-center gap-3 text-sm">
                      <span className="w-32 shrink-0 text-zinc-300 truncate">{cat.category}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className="h-full bg-emerald-500/70 rounded-full"
                          style={{ width: `${Math.min(cat.percentage, 100)}%` }}
                        />
                      </div>
                      <span className="text-zinc-500 text-xs w-24 text-right shrink-0 font-figures">
                        {formatCurrency(cat.total)} ({cat.percentage.toFixed(0)}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Principal descoberta — "O que mudou? Existe algum
            comportamento que merece atenção?" Cor própria (roxo "ai",
            não o verde do dinheiro) pra deixar claro que é uma leitura
            da IA sobre os dados, não um número bruto da conta. */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-zinc-300">
            <Sparkles className="text-ai-400" size={18} />
            Principal descoberta
          </h2>
          <div className="p-6 rounded-xl border border-ai-500/25 bg-ai-500/[0.07] relative overflow-hidden">
            <div className="absolute -top-10 -right-10 w-40 h-40 bg-ai-500/10 rounded-full blur-3xl" aria-hidden="true" />
            {loading ? (
              <div className="space-y-3 relative">
                <div className="h-4 bg-ai-500/10 rounded w-full animate-pulse" />
                <div className="h-4 bg-ai-500/10 rounded w-5/6 animate-pulse" />
                <div className="h-4 bg-ai-500/10 rounded w-4/6 animate-pulse" />
              </div>
            ) : heroInsight ? (
              <div className="relative space-y-2 animate-fade-slide-up">
                <p className="text-ai-400 text-[11px] font-bold uppercase tracking-widest">Descoberta do mês</p>
                <h3 className="text-zinc-50 text-xl font-bold leading-snug">{heroInsight.title}</h3>
                <p className="text-zinc-300 text-sm leading-relaxed">{heroInsight.message}</p>
                <ExplanationBlock insight={heroInsight} tone="hero" />
              </div>
            ) : (
              <div className="relative space-y-1 animate-fade-slide-up">
                <p className="text-zinc-200 text-base leading-relaxed">{data?.alerta}</p>
                <p className="text-zinc-500 text-xs">
                  Nenhum padrão específico se destacou este mês — o que, por si só, já é uma boa notícia.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Comparações — "Onde estou gastando mais? Como isso evoluiu?" */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-zinc-300">
            <TrendingUp className="text-emerald-500" size={20} />
            Comparações
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 p-6 rounded-xl border border-zinc-800 bg-zinc-900/50 h-[300px] w-full relative">
              {loading ? (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="flex flex-col items-center gap-2">
                    <div className="w-8 h-8 border-2 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin" />
                    <span className="text-zinc-500 text-sm">Carregando histórico...</span>
                  </div>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data?.historico}>
                    <defs>
                      <linearGradient id="colorValor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                    <XAxis dataKey="mes" stroke="#71717a" fontSize={12} tickLine={false} axisLine={false} dy={10} />
                    <YAxis
                      stroke="#71717a"
                      fontSize={12}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => `R$ ${value}`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a", borderRadius: "8px" }}
                      itemStyle={{ color: "#10b981" }}
                      labelStyle={{ color: "#71717a", marginBottom: "4px" }}
                      formatter={(value: number) => [formatCurrency(value), "Gastos"]}
                    />
                    <Area
                      type="monotone"
                      dataKey="valor"
                      stroke="#10b981"
                      strokeWidth={3}
                      fillOpacity={1}
                      fill="url(#colorValor)"
                      animationDuration={800}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="p-6 rounded-xl border border-zinc-800 bg-zinc-900/50 flex flex-col justify-between gap-4">
              <StatRow
                label="Previsão próximo mês"
                value={!loading && data ? formatCurrency(data.previsao_proximo_mes) : null}
                icon={Target}
              />
              <StatRow
                label="Economia sugerida"
                value={!loading && data ? formatCurrency(data.economias_sugeridas) : null}
                icon={PiggyBank}
              />
              <StatRow
                label="Média mensal"
                value={!loading && data ? formatCurrency(data.media_gastos) : null}
                icon={TrendingUp}
              />
              <StatRow
                label="Variação"
                value={
                  !loading && data
                    ? `${data.variacao_percentual > 0 ? "+" : ""}${data.variacao_percentual}%`
                    : null
                }
                icon={data && data.variacao_percentual > 0 ? TrendingUp : TrendingDown}
                valueClassName={
                  data && data.variacao_percentual > 0 ? "text-rose-400" : "text-emerald-400"
                }
              />
            </div>
          </div>
        </section>

        {/* Análises detalhadas — o restante das descobertas, cada uma
            com sua explicabilidade quando existir. */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-zinc-300">
            <CheckCircle2 className="text-emerald-500" size={20} />
            Análises detalhadas
          </h2>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="p-4 rounded-lg bg-zinc-900 border border-zinc-800 h-24 animate-pulse" />
              ))}
            </div>
          ) : restInsights.length === 0 ? (
            <div className="p-6 rounded-lg bg-zinc-900 border border-zinc-800 text-center text-sm text-zinc-500">
              {heroInsight
                ? "Por enquanto essa foi a única descoberta relevante deste mês."
                : "Nenhuma análise disponível ainda. Adicione mais transações para liberar insights."}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {restInsights.map((insight, idx) => (
                <div key={insight.id} style={{ animationDelay: `${idx * 60}ms` }} className="animate-fade-slide-up">
                  <InsightCard insight={insight} />
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </AppLayout>
  );
}

function StatRow({
  label,
  value,
  icon: Icon,
  valueClassName,
}: {
  label: string;
  value: string | null;
  icon: typeof Target;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs text-zinc-500 flex items-center gap-1.5">
        <Icon size={13} className="text-zinc-600 shrink-0" />
        {label}
      </p>
      {value === null ? (
        <div className="h-4 w-16 bg-zinc-800 rounded animate-pulse" />
      ) : (
        <p className={`font-figures text-sm font-bold ${valueClassName ?? "text-white"}`}>{value}</p>
      )}
    </div>
  );
}

const INSIGHT_ICON: Record<InsightEntry["type"], typeof AlertCircle> = {
  expense: AlertCircle,
  income: TrendingUp,
  cashflow: TrendingDown,
  goal: Target,
  risk: AlertCircle,
  opportunity: CheckCircle2,
};

const SEVERITY_COLOR: Record<InsightEntry["severity"], string> = {
  high: "text-rose-500",
  medium: "text-amber-500",
  low: "text-emerald-500",
};

/** Bloco de explicabilidade (período atual vs. anterior, diferença e
    principais responsáveis) — compartilhado entre o card de destaque
    (tone="hero") e os cards de análises detalhadas (tone="card"), pra
    não duplicar a lógica em dois lugares com aparência diferente.
    O rótulo/valor resumido (metric_label/metric_value) é independente
    da explicação detalhada — um insight pode ter só um dos dois, ou
    os dois ao mesmo tempo. */
function ExplanationBlock({ insight, tone }: { insight: InsightEntry; tone: "hero" | "card" }) {
  const border = tone === "hero" ? "border-ai-500/20" : "border-zinc-800/70";
  const labelColor = tone === "hero" ? "text-ai-300/70" : "text-zinc-500";

  return (
    <>
      {insight.metric_label && insight.metric_value && (
        <p className={`text-[11px] mt-1.5 uppercase tracking-wide ${tone === "hero" ? "text-ai-300/70" : "text-zinc-500"}`}>
          {insight.metric_label}:{" "}
          <span className={`normal-case ${tone === "hero" ? "text-zinc-200" : "text-zinc-300"}`}>
            {insight.metric_value}
          </span>
        </p>
      )}

      {insight.explanation && (
        <div className={`mt-4 pt-4 border-t ${border} grid grid-cols-1 sm:grid-cols-3 gap-3`}>
          <div className="flex sm:flex-col gap-4 sm:gap-1.5 sm:col-span-2">
            <div>
              <p className={`text-[10px] uppercase tracking-wide ${labelColor}`}>
                {insight.explanation.previous_period_label}
              </p>
              <p className="text-sm text-zinc-400">{formatCurrency(insight.explanation.previous_value)}</p>
            </div>
            <div>
              <p className={`text-[10px] uppercase tracking-wide ${labelColor}`}>
                {insight.explanation.current_period_label}
              </p>
              <p className="text-sm text-zinc-200 font-semibold">
                {formatCurrency(insight.explanation.current_value)}
              </p>
            </div>
            <div>
              <p className={`text-[10px] uppercase tracking-wide ${labelColor}`}>Diferença</p>
              <p
                className={`text-sm font-semibold ${insight.explanation.difference >= 0 ? "text-rose-400" : "text-emerald-400"}`}
              >
                {insight.explanation.difference >= 0 ? "+" : ""}
                {formatCurrency(insight.explanation.difference)}
              </p>
            </div>
          </div>
          {insight.explanation.top_contributors.length > 0 && (
            <div>
              <p className={`text-[10px] uppercase tracking-wide mb-1 ${labelColor}`}>Principais responsáveis</p>
              <ul className="space-y-0.5">
                {insight.explanation.top_contributors.map((c) => (
                  <li key={c.label} className="text-xs text-zinc-400 flex justify-between gap-2">
                    <span className="truncate">{c.label}</span>
                    <span className="text-zinc-500 shrink-0 font-figures">{formatCurrency(c.value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function InsightCard({ insight }: { insight: InsightEntry }) {
  const Icon = INSIGHT_ICON[insight.type] ?? Info;
  const color = SEVERITY_COLOR[insight.severity] ?? "text-zinc-400";

  return (
    <div
      className={`p-4 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors ${
        insight.explanation ? "md:col-span-3" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <Icon className={`${color} shrink-0 mt-1`} size={18} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-zinc-300 font-bold mb-1">{insight.title}</p>
          <p className="text-xs text-zinc-500 leading-relaxed">{insight.message}</p>
          <ExplanationBlock insight={insight} tone="card" />
        </div>
      </div>
    </div>
  );
}
