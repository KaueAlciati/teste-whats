"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";

import { ArrowUpRight, ArrowDownRight, DollarSign, Sparkles } from "lucide-react";
import Link from "next/link";

import { TransactionList } from "@/components/TransactionList";
import { storage } from "@/lib/storage";
import type { InsightData, DashboardSummary } from "@/lib/api";
import { AppLayout } from "@/components/AppLayout";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";

const FinanceChart = dynamic(
  () => import("@/components/FinanceChart").then((mod) => mod.FinanceChart),
  {
    ssr: false,
    loading: () => (
      <div className="h-[300px] w-full bg-zinc-900/50 rounded-xl animate-pulse flex items-center justify-center text-zinc-500">
        Carregando gráfico...
      </div>
    ),
  },
);

interface SummaryCardProps {
  title: string;
  amount: string;
  icon: React.ReactNode;
  percentage?: number;
  type?: "income" | "expense" | "balance";
  getTrendAnalysis?: (
    value: number | undefined,
    type: "income" | "expense" | "balance",
  ) => string;
  /** O Saldo Total é o número mais importante da tela — ganha um
      tratamento visual levemente diferente (borda e fundo com a cor de
      marca) pra guiar o olho até ele primeiro, em vez dos três cartões
      competirem com o mesmo peso visual. */
  highlight?: boolean;
}

export default function Home() {
  const [summary, setSummary] = useState<DashboardSummary>({
    incomes: 0,
    expenses: 0,
    total: 0,
    balance_trend_percentage: 0,
    income_trend_percentage: 0,
    expense_trend_percentage: 0,
    expense_ratio: 0,
  });

  const [insight, setInsight] = useState<InsightData | null>(null);
  const handleFetchError = useHandleFetchError();

  const fetchData = useCallback(async () => {
    try {
      const [summaryData, insightData] = await Promise.all([
        storage.getSummary(),
        storage.getInsights(),
      ]);

      setSummary(summaryData);
      setInsight(insightData);
    } catch (error) {
      await handleFetchError(error, "Erro ao buscar dados do dashboard:");
    }
  }, [handleFetchError]);

  useEffect(() => {
    fetchData();

    // Sem isso, os cards de Saldo/Entradas/Saídas e o Insight da IA
    // ficavam "presos" nos valores de quando a página carregou —
    // só atualizavam depois de um F5 manual.
    window.addEventListener("transactions-changed", fetchData);
    return () => window.removeEventListener("transactions-changed", fetchData);
  }, [fetchData]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
    }).format(value);
  };

  const getTrendAnalysis = (
    value: number | undefined,
    type: "income" | "expense" | "balance",
  ) => {
    if (value === undefined || value === null) {
      return "Sem dados suficientes ainda.";
    }

    const absValue = Math.abs(value);

    if (type === "balance") {
      if (value > 0) {
        return `Seu saldo melhorou ${absValue}% em relação ao mês anterior.`;
      }
      if (value < 0) {
        return `Seu saldo piorou ${absValue}% em relação ao mês anterior.`;
      }
      return "Seu saldo se manteve estável em relação ao mês anterior.";
    }

    if (type === "income") {
      if (value > 0) {
        return `Suas entradas subiram ${absValue}% em relação ao mês anterior.`;
      }

      if (value < 0) {
        return `Suas entradas caíram ${absValue}% em relação ao mês anterior.`;
      }

      return "Suas entradas estão estáveis.";
    }

    if (type === "expense") {
      if (value > 0) {
        return `Seus gastos subiram ${absValue}% em relação ao mês anterior.`;
      }

      if (value < 0) {
        return `Seus gastos caíram ${absValue}% em relação ao mês anterior.`;
      }

      return "Seus gastos se mantiveram constantes.";
    }

    return "Sem dados suficientes.";
  };

  return (
    <AppLayout>
      <main className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Dashboard</h1>

        <p className="text-zinc-400 text-sm">
          Acompanhe sua saúde financeira e insights de IA.
        </p>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
        <SummaryCard
          title="Saldo Total"
          amount={formatCurrency(summary.total)}
          icon={<DollarSign size={20} />}
          percentage={summary.balance_trend_percentage}
          type="balance"
          getTrendAnalysis={getTrendAnalysis}
          highlight
        />

        <SummaryCard
          title="Entradas"
          amount={formatCurrency(summary.incomes)}
          icon={<ArrowUpRight size={20} />}
          percentage={summary.income_trend_percentage}
          type="income"
          getTrendAnalysis={getTrendAnalysis}
        />

        <SummaryCard
          title="Saídas"
          amount={formatCurrency(summary.expenses)}
          icon={<ArrowDownRight size={20} />}
          percentage={summary.expense_trend_percentage}
          type="expense"
          getTrendAnalysis={getTrendAnalysis}
        />
      </section>

      <section>
        <FinanceChart />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TransactionList />

        {/* Cor própria (roxo "ai", não o verde do dinheiro): sinaliza que
            este bloco é uma leitura da IA sobre os dados, não um número
            bruto da sua conta — a mesma distinção que separa "extrato" de
            "opinião" num relatório financeiro de verdade. */}
        <div className="bg-ai-500/[0.07] border border-ai-500/25 rounded-xl p-6 flex flex-col justify-center relative overflow-hidden">
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-ai-500/10 rounded-full blur-3xl" aria-hidden="true" />
          <h3 className="text-ai-300 font-bold mb-2 flex items-center gap-2 relative">
            <Sparkles size={16} className="text-ai-400" />
            Insight da IA
          </h3>

          {insight?.ai_enabled === false ? (
            // Antes, desligar "Insights Semanais da IA" em Configurações
            // não mudava nada aqui — o card continuava mostrando os
            // últimos números calculados, dando a entender que a IA
            // ainda estava ativa. Agora reflete o estado real.
            <div className="space-y-2 relative">
              <p className="text-zinc-300 text-sm leading-relaxed">
                {insight.alerta}
              </p>
              <Link
                href="/settings"
                className="inline-block text-xs font-medium text-ai-300 hover:text-ai-200 underline underline-offset-2"
              >
                Reativar em Configurações
              </Link>
            </div>
          ) : insight ? (
            <div className="space-y-3 relative">
              <p className="text-zinc-300 text-sm leading-relaxed">
                {insight.alerta}
              </p>

              <div className="grid grid-cols-2 gap-4 mt-2">
                <div>
                  <p className="text-xs text-zinc-500 uppercase font-bold">
                    Previsão
                  </p>

                  <p className="font-figures text-ai-300 font-bold">
                    {formatCurrency(insight.previsao_proximo_mes)}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-zinc-500 uppercase font-bold">
                    Economia
                  </p>

                  <p className="font-figures text-ai-300 font-bold">
                    {formatCurrency(insight.economias_sugeridas)}
                  </p>
                </div>
              </div>

              <Link
                href="/insights"
                className="inline-block text-xs font-medium text-ai-300 hover:text-ai-200 underline underline-offset-2"
              >
                Ver todos os insights
              </Link>
            </div>
          ) : (
            <div className="space-y-2 relative">
              <p className="text-zinc-300 text-sm leading-relaxed">
                Ainda não há dados suficientes.
              </p>

              <p className="text-zinc-500 text-xs">
                Adicione transações para gerar insights automáticos.
              </p>
            </div>
          )}
        </div>
      </section>
    </main>
    </AppLayout>
  );
}

function SummaryCard({
  title,
  amount,
  icon,
  percentage,
  type,
  getTrendAnalysis,
  highlight,
}: SummaryCardProps) {
  const hasData = percentage !== undefined && percentage !== null;

  const analysis =
    hasData && type && getTrendAnalysis
      ? getTrendAnalysis(percentage, type)
      : "Nenhuma movimentação registrada ainda.";

  const getTrendColor = () => {
    if (!hasData) {
      return "text-zinc-500";
    }

    if (percentage === 0) {
      return "text-zinc-400";
    }

    if (type === "income" || type === "balance") {
      return percentage > 0 ? "text-emerald-500" : "text-rose-500";
    }

    if (type === "expense") {
      return percentage > 0 ? "text-rose-500" : "text-emerald-500";
    }

    return "text-zinc-500";
  };

  return (
    <div
      className={`p-6 rounded-xl border space-y-3 transition-colors ${
        highlight
          ? "border-emerald-500/30 bg-gradient-to-br from-emerald-500/[0.08] to-zinc-900/50 hover:border-emerald-500/50"
          : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
      }`}
    >
      <div className="flex justify-between items-center text-zinc-400">
        <span className="text-sm font-medium">{title}</span>

        <div className={`p-1.5 rounded-md ${highlight ? "bg-emerald-500/15 text-emerald-400" : "bg-zinc-800"}`}>
          {icon}
        </div>
      </div>

      <h2 className="font-figures text-3xl font-bold tracking-tight">{amount}</h2>

      <div className={`text-xs font-medium leading-relaxed ${getTrendColor()}`}>
        {analysis}
      </div>
    </div>
  );
}
