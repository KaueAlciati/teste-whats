"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { storage } from "@/lib/storage";
import { HttpError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import type {
  ChartDataPoint,
  DashboardSummary,
  Goal,
  InsightData,
  Transaction,
} from "@/lib/api";

interface DataContextType {
  transactions: Transaction[];
  goals: Goal[];
  summary: DashboardSummary;
  insights: InsightData | null;
  chartData: ChartDataPoint[];
  loading: boolean;
  refreshAll: () => Promise<void>;
  refreshTransactions: () => Promise<void>;
  refreshGoals: () => Promise<void>;
  refreshSummary: () => Promise<void>;
  refreshInsights: () => Promise<void>;
  refreshChartData: () => Promise<void>;
}

const DataContext = createContext<DataContextType | undefined>(undefined);

export function DataProvider({ children }: { children: ReactNode }) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [summary, setSummary] = useState<DashboardSummary>({
    incomes: 0,
    expenses: 0,
    total: 0,
    balance_trend_percentage: 0,
    income_trend_percentage: 0,
    expense_trend_percentage: 0,
    expense_ratio: 0,
  });
  const [insights, setInsights] = useState<InsightData | null>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const { logout } = useAuth();
  const { addToast } = useToast();

  const withLoading = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
      setLoading(true);
      try {
        return await action();
      } catch (err) {
        if (err instanceof HttpError && err.status === 401) {
          // Sessão inválida/expirada de verdade (não é "sem dados") —
          // desloga e deixa o ProtectedRoute redirecionar para o login,
          // em vez de mostrar telas vazias como se o usuário não
          // tivesse nenhuma transação/meta cadastrada.
          addToast("warning", "Sua sessão expirou. Faça login novamente.");
          await logout();
        } else {
          const message =
            err instanceof HttpError
              ? "Não foi possível carregar seus dados agora. Tente novamente."
              : "Erro inesperado ao carregar seus dados.";
          addToast("error", message);
          console.error("Erro ao carregar dados:", err);
        }
        return undefined;
      } finally {
        setLoading(false);
      }
    },
    [logout, addToast],
  );

  const fetchTransactions = useCallback(async () => {
    const data = await storage.getTransactions();
    setTransactions(data);
  }, []);

  const fetchGoals = useCallback(async () => {
    const data = await storage.getGoalsStatus();
    setGoals(data);
  }, []);

  const fetchSummary = useCallback(async () => {
    const data = await storage.getSummary();
    setSummary(data);
  }, []);

  const fetchInsights = useCallback(async () => {
    const data = await storage.getInsights();
    setInsights(data);
  }, []);

  const fetchChartData = useCallback(async () => {
    const data = await storage.getChartData();
    setChartData(data);
  }, []);

  const refreshTransactions = useCallback(
    async () => withLoading(fetchTransactions),
    [fetchTransactions, withLoading],
  );

  const refreshGoals = useCallback(
    async () => withLoading(fetchGoals),
    [fetchGoals, withLoading],
  );

  const refreshSummary = useCallback(
    async () => withLoading(fetchSummary),
    [fetchSummary, withLoading],
  );

  const refreshInsights = useCallback(
    async () => withLoading(fetchInsights),
    [fetchInsights, withLoading],
  );

  const refreshChartData = useCallback(
    async () => withLoading(fetchChartData),
    [fetchChartData, withLoading],
  );

  const refreshAll = useCallback(async () => {
    await withLoading(async () => {
      await Promise.all([
        fetchTransactions(),
        fetchGoals(),
        fetchSummary(),
        fetchInsights(),
        fetchChartData(),
      ]);
    });
  }, [fetchChartData, fetchGoals, fetchInsights, fetchSummary, fetchTransactions, withLoading]);

  return (
    <DataContext.Provider
      value={{
        transactions,
        goals,
        summary,
        insights,
        chartData,
        loading,
        refreshAll,
        refreshTransactions,
        refreshGoals,
        refreshSummary,
        refreshInsights,
        refreshChartData,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const context = useContext(DataContext);
  if (context === undefined) {
    throw new Error("useData must be used within a DataProvider");
  }
  return context;
}
