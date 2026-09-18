import type {
  Transaction,
  Goal,
  InsightData,
  InsightEntry,
  DashboardSummary,
  ChartDataPoint,
  UserProfile,
  UserSettings,
  AuthSession,
  ImportPreviewResponse,
  ImportPreviewRow,
  ImportConfirmRow,
  ImportConfirmResponse,
  ImportBatchSummary,
  MonthlySummary,
} from "./api";
import { formatCategoryLabel, normalizeCategoryKey, suggestCategory } from "./category";
import { computeDedupeHash, normalizeDescription } from "./dedupe";
import {
  FileValidationError,
  parseCsv,
  validateCsvFile,
} from "./csvImport";
import {
  NotificationCategory,
  NotificationPriority,
  NotificationStatus,
  type Notification,
  type ListNotificationsRequest,
  type ListNotificationsResponse,
  type MarkAllNotificationsAsReadRequest,
  type MarkNotificationAsReadResponse,
  type MarkAllNotificationsAsReadResponse,
} from "@/features/notifications/types";

const LS_KEY_PREFIX = "financeai";
const LS_KEY_USERS = `${LS_KEY_PREFIX}.users`;
const LS_KEY_CURRENT_LOCAL_USER_ID = `${LS_KEY_PREFIX}.currentLocalUserId`;
const LS_KEY_SETTINGS = `${LS_KEY_PREFIX}.settings`;

const MONTH_NAMES = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];

// Registro interno de transação no modo local: além dos campos
// públicos (Transaction), guarda metadados usados só para
// deduplicação/importação — nunca expostos fora deste módulo além
// do necessário (o objeto retornado ao chamador continua satisfazendo
// o tipo `Transaction`, os campos extras é que habilitam checar
// duplicidade em importações futuras, igual ao backend).
type LocalTransactionRecord = Transaction & {
  dedupe_hash?: string;
  external_id?: string | null;
  import_batch_id?: number;
  original_description?: string;
};

type LocalImportBatch = {
  id: number;
  filename: string;
  source: "csv";
  status: "preview" | "completed";
  total: number;
  new_count: number;
  duplicated_count: number;
  error_count: number;
  imported_count: number;
  created_at: string;
  completed_at?: string | null;
};

type LocalStagedRow = ImportPreviewRow & {
  batch_id: number;
  date_iso: string | null;
  normalized_description: string | null;
  dedupe_hash: string | null;
  external_id: string | null;
};

type LocalUserRecord = {
  id: number;
  name: string;
  email: string;
  passwordHash: string;
  passwordSalt: string;
  createdAt: string;
};

type LocalNotificationsService = {
  list: (params: ListNotificationsRequest) => Promise<ListNotificationsResponse>;
  markAsRead: (id: number) => Promise<MarkNotificationAsReadResponse>;
  markAllAsRead: (
    params: MarkAllNotificationsAsReadRequest,
  ) => Promise<MarkAllNotificationsAsReadResponse>;
};

function getLs(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Não foi possível ler o arquivo."));
    reader.readAsText(file, "utf-8");
  });
}

function userKey(userId: number, suffix: string): string {
  return `${LS_KEY_PREFIX}.user.${userId}.${suffix}`;
}

function readLs<T>(key: string, fallback: T): T {
  const ls = getLs();
  if (!ls) return fallback;
  try {
    const raw = ls.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeLs<T>(key: string, value: T): void {
  const ls = getLs();
  if (!ls) return;
  try {
    ls.setItem(key, JSON.stringify(value));
  } catch {
    // ignore quota errors
  }
}

async function sha256(text: string): Promise<string> {
  const enc = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", enc);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

function generateSalt(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function nextId(list: { id?: number }[]): number {
  const max = list.reduce((m, item) => Math.max(m, item.id ?? 0), 0);
  return max + 1;
}

function getCurrentLocalUserId(): number | null {
  return readLs<number | null>(LS_KEY_CURRENT_LOCAL_USER_ID, null);
}

function setCurrentLocalUserId(id: number | null): void {
  if (id === null) {
    const ls = getLs();
    if (ls) ls.removeItem(LS_KEY_CURRENT_LOCAL_USER_ID);
  } else {
    writeLs(LS_KEY_CURRENT_LOCAL_USER_ID, id);
  }
}

function requireCurrentUserId(): number {
  const id = getCurrentLocalUserId();
  if (id === null) throw new Error("Nenhum usuário local logado");
  return id;
}

function computeGoalDerived(
  goal: Omit<Goal, "missing" | "percent"> & { missing?: number; percent?: number },
): Goal {
  const current = goal.current ?? 0;
  const target = Math.max(goal.target, 0.01);
  const percent = Math.min(100, (current / target) * 100);
  const missing = Math.max(0, target - current);
  return {
    ...goal,
    current,
    missing,
    percent: Math.round(percent * 100) / 100,
    completed: goal.completed ?? percent >= 100,
  } as Goal;
}

function sortTransactionsByDateDesc(txs: Transaction[]): Transaction[] {
  return [...txs].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
  );
}

function buildUserTransactionsKey(userId: number): string {
  return userKey(userId, "transactions");
}
function buildUserGoalsKey(userId: number): string {
  return userKey(userId, "goals");
}
function buildUserNotificationsKey(userId: number): string {
  return userKey(userId, "notifications");
}
function buildUserImportBatchesKey(userId: number): string {
  return userKey(userId, "importBatches");
}
function buildUserStagedRowsKey(userId: number): string {
  return userKey(userId, "importStagedRows");
}

function loadTransactions(userId: number): LocalTransactionRecord[] {
  return readLs<LocalTransactionRecord[]>(buildUserTransactionsKey(userId), []);
}

function saveTransactions(userId: number, list: LocalTransactionRecord[]): void {
  writeLs(buildUserTransactionsKey(userId), list);
}

function loadImportBatches(userId: number): LocalImportBatch[] {
  return readLs<LocalImportBatch[]>(buildUserImportBatchesKey(userId), []);
}

function saveImportBatches(userId: number, list: LocalImportBatch[]): void {
  writeLs(buildUserImportBatchesKey(userId), list);
}

function loadStagedRows(userId: number): LocalStagedRow[] {
  return readLs<LocalStagedRow[]>(buildUserStagedRowsKey(userId), []);
}

function saveStagedRows(userId: number, list: LocalStagedRow[]): void {
  writeLs(buildUserStagedRowsKey(userId), list);
}

function loadGoals(userId: number): Goal[] {
  const raw = readLs<Array<Partial<Goal>>>(buildUserGoalsKey(userId), []);
  return raw.map((g) => computeGoalDerived(g as Omit<Goal, "missing" | "percent">));
}

function saveGoals(userId: number, list: Goal[]): void {
  writeLs(buildUserGoalsKey(userId), list);
}

function loadNotifications(userId: number): Notification[] {
  return readLs<Notification[]>(buildUserNotificationsKey(userId), []);
}

function saveNotifications(userId: number, list: Notification[]): void {
  writeLs(buildUserNotificationsKey(userId), list);
}

/**
 * Mesma regra do backend (`finance_service.get_dashboard_summary`),
 * portada para o modo local: cada cartão (Saldo, Entradas, Saídas)
 * tem sua própria tendência mês a mês — antes, os três campos de
 * tendência sempre vinham fixos em 0 no LocalStorage.
 */
function computeDashboardSummary(txs: Transaction[]): DashboardSummary {
  const incomes = round2(
    txs.filter((t) => t.type === "income").reduce((acc, t) => acc + (t.amount ?? 0), 0),
  );
  const expenses = round2(
    txs.filter((t) => t.type === "expense").reduce((acc, t) => acc + (t.amount ?? 0), 0),
  );
  const total = round2(incomes - expenses);

  const monthlyBalance = new Map<string, number>();
  const monthlyIncomes = new Map<string, number>();
  const monthlyExpenses = new Map<string, number>();
  for (const tx of txs) {
    const monthKey = monthKeyOf(tx.date);
    const amount = tx.amount ?? 0;
    if (tx.type === "income") {
      monthlyBalance.set(monthKey, (monthlyBalance.get(monthKey) ?? 0) + amount);
      monthlyIncomes.set(monthKey, (monthlyIncomes.get(monthKey) ?? 0) + amount);
    } else {
      monthlyBalance.set(monthKey, (monthlyBalance.get(monthKey) ?? 0) - amount);
      monthlyExpenses.set(monthKey, (monthlyExpenses.get(monthKey) ?? 0) + amount);
    }
  }

  // Compara o mês mais recente com o mês anterior a ele — calculado
  // separadamente pra saldo, entradas e saídas, pra cada cartão do
  // Dashboard mostrar a própria variação (não a de despesas reaproveitada).
  function monthOverMonthTrend(monthlyValues: Map<string, number>): number {
    const ordered = Array.from(monthlyValues.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, v]) => v);
    if (ordered.length < 2) return 0;
    const prev = ordered[ordered.length - 2];
    const curr = ordered[ordered.length - 1];
    if (prev === 0) return 0;
    return Math.round(((curr - prev) / Math.abs(prev)) * 1000) / 10;
  }

  const balance_trend_percentage = monthOverMonthTrend(monthlyBalance);
  const income_trend_percentage = monthOverMonthTrend(monthlyIncomes);
  const expense_trend_percentage = monthOverMonthTrend(monthlyExpenses);

  // Igual ao backend: sem receita no período, o percentual comprometido
  // não tem contra o que ser calculado (0), em vez do valor artificialmente
  // alto que a fórmula anterior (dividindo por um denominador mínimo de 1)
  // podia produzir.
  const expense_ratio = incomes > 0 ? round2((expenses / incomes) * 100) : 0;

  return {
    incomes,
    expenses,
    total,
    balance_trend_percentage,
    income_trend_percentage,
    expense_trend_percentage,
    expense_ratio,
  };
}

function computeChartData(txs: Transaction[]): ChartDataPoint[] {
  const byMonth = new Map<string, { name: string; income: number; expense: number }>();

  const now = new Date();
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    byMonth.set(key, {
      name: MONTH_NAMES[d.getMonth()],
      income: 0,
      expense: 0,
    });
  }

  for (const tx of txs) {
    const d = new Date(tx.date);
    if (Number.isNaN(d.getTime())) continue;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const bucket = byMonth.get(key);
    if (!bucket) continue;
    if (tx.type === "income") bucket.income += tx.amount ?? 0;
    else bucket.expense += tx.amount ?? 0;
  }

  return Array.from(byMonth.values());
}

function monthKeyOf(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function forecastEndOfMonth(currentValue: number, today: Date): number {
  const day = today.getDate();
  if (day <= 0) return round2(currentValue);
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  const dailyAverage = currentValue / day;
  return round2(dailyAverage * daysInMonth);
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Mesma análise estatística do backend (`insight_service.py`), portada
 * para o modo local/offline: categoria dominante, despesa recorrente,
 * pressão de fluxo de caixa, tendência de receita, projeção de metas
 * e risco de déficit — usando os dados reais já salvos neste
 * navegador. Antes, o modo local sempre devolvia `insights: []`.
 */
function computeInsights(txs: Transaction[], goals: Goal[]): InsightData | null {
  const expenses = txs.filter((t) => t.type === "expense");
  if (expenses.length === 0) return null;

  const byMonthMap = new Map<string, number>();
  const sortedTxs = [...expenses].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
  for (const tx of sortedTxs) {
    const key = monthKeyOf(tx.date);
    byMonthMap.set(key, (byMonthMap.get(key) ?? 0) + (tx.amount ?? 0));
  }

  const historico: { mes: string; valor: number }[] = Array.from(
    byMonthMap.entries(),
  )
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, valor]) => {
      const [y, m] = key.split("-");
      const monthIndex = parseInt(m, 10) - 1;
      return {
        mes: `${MONTH_NAMES[monthIndex]}/${y.slice(2)}`,
        valor: round2(valor),
      };
    })
    .slice(-6);

  if (historico.length === 0) return null;

  const values = historico.map((h) => h.valor);
  const media_gastos = round2(values.reduce((a, b) => a + b, 0) / values.length);

  let variacao_percentual = 0;
  if (values.length >= 2) {
    const prev = values[values.length - 2] || 1;
    const curr = values[values.length - 1];
    variacao_percentual = Math.round(((curr - prev) / prev) * 10000) / 100;
  }

  let alerta: string;
  if (variacao_percentual > 15) {
    alerta = `Atenção: seus gastos aumentaram ${variacao_percentual.toFixed(1)}% em relação ao mês anterior. Considere revisar despesas variáveis.`;
  } else if (variacao_percentual < -10) {
    alerta = `Ótima notícia! Seus gastos caíram ${Math.abs(variacao_percentual).toFixed(1)}%. Considere direcionar a economia para suas metas.`;
  } else {
    alerta = `Seus gastos estão estáveis (${variacao_percentual.toFixed(1)}% de variação). Continue acompanhando para manter o equilíbrio financeiro.`;
  }

  // --- Análises por regra, mesma lógica do backend ---
  const today = new Date();
  const currentMonthKey = monthKeyOf(today.toISOString());
  const previousMonthDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const previousMonthKey = monthKeyOf(previousMonthDate.toISOString());

  const monthlyExpenses = new Map<string, number>();
  const monthlyIncomes = new Map<string, number>();
  const monthlyCategoryExpenses = new Map<string, Map<string, number>>();
  // [monthKey][categoryKey] -> Map(descriptionKey -> total) — só pra
  // explicar (seção 12 do prompt) o insight de mudança de
  // comportamento: quais descrições concretas empurraram o gasto.
  const categoryDescriptionTotals = new Map<string, Map<string, Map<string, number>>>();
  const categoryLabels = new Map<string, string>();
  const recurringCounter = new Map<string, number>();
  const recurringAmounts = new Map<string, number>();

  for (const tx of txs) {
    const monthKey = monthKeyOf(tx.date);
    const amount = tx.amount ?? 0;

    if (tx.type === "expense") {
      const descKey = (tx.description ?? "").trim().toLowerCase();
      const categoryKey = normalizeCategoryKey(tx.category);
      if (!categoryLabels.has(categoryKey)) {
        categoryLabels.set(categoryKey, formatCategoryLabel(tx.category));
      }

      monthlyExpenses.set(monthKey, (monthlyExpenses.get(monthKey) ?? 0) + amount);
      const catMap = monthlyCategoryExpenses.get(monthKey) ?? new Map<string, number>();
      catMap.set(categoryKey, (catMap.get(categoryKey) ?? 0) + amount);
      monthlyCategoryExpenses.set(monthKey, catMap);

      const catDescMap = categoryDescriptionTotals.get(monthKey) ?? new Map<string, Map<string, number>>();
      const descMap = catDescMap.get(categoryKey) ?? new Map<string, number>();
      descMap.set(descKey, (descMap.get(descKey) ?? 0) + amount);
      catDescMap.set(categoryKey, descMap);
      categoryDescriptionTotals.set(monthKey, catDescMap);

      recurringCounter.set(descKey, (recurringCounter.get(descKey) ?? 0) + 1);
      recurringAmounts.set(descKey, (recurringAmounts.get(descKey) ?? 0) + amount);
    } else {
      monthlyIncomes.set(monthKey, (monthlyIncomes.get(monthKey) ?? 0) + amount);
    }
  }

  const currentExpenses = monthlyExpenses.get(currentMonthKey) ?? 0;
  const currentIncomes = monthlyIncomes.get(currentMonthKey) ?? 0;
  const previousIncomes = monthlyIncomes.get(previousMonthKey) ?? 0;

  const forecastExpenses = forecastEndOfMonth(currentExpenses, today);
  const previsao_proximo_mes = round2(Math.max(forecastExpenses, media_gastos));
  const economias_sugeridas = round2(Math.max(currentExpenses - media_gastos, 0) * 0.35);

  const insights: InsightEntry[] = [];

  const currentCategoryMap = monthlyCategoryExpenses.get(currentMonthKey);
  if (currentCategoryMap && currentCategoryMap.size > 0) {
    let topKey: string | null = null;
    let topTotal = 0;
    for (const [key, total] of currentCategoryMap.entries()) {
      if (topKey === null || total > topTotal) {
        topKey = key;
        topTotal = total;
      }
    }
    if (topKey) {
      const label = categoryLabels.get(topKey) ?? topKey;
      const share = currentExpenses > 0 ? (topTotal / currentExpenses) * 100 : 0;
      insights.push({
        id: "top-category",
        type: "expense",
        severity: share >= 35 ? "high" : "medium",
        title: "Categoria dominante de gasto",
        message: `${label} concentrou ${share.toFixed(0)}% das saídas do mês, somando R$ ${topTotal.toFixed(2)}.`,
        metric_label: "Maior categoria",
        metric_value: label,
      });
    }
  }

  // Análise de comportamento: qual categoria mais aumentou de gasto em
  // relação ao mês anterior, com explicabilidade — só gera quando há
  // base no mês anterior pra comparar (evita "falsa precisão").
  const previousCategoryMap = monthlyCategoryExpenses.get(previousMonthKey);
  if (currentCategoryMap && previousCategoryMap) {
    let behaviorKey: string | null = null;
    let behaviorDiff = 0;
    let behaviorCurrent = 0;
    let behaviorPrevious = 0;
    for (const [key, currentAmount] of currentCategoryMap.entries()) {
      const previousAmount = previousCategoryMap.get(key) ?? 0;
      if (previousAmount <= 0) continue;
      const diff = currentAmount - previousAmount;
      if (diff > behaviorDiff) {
        behaviorDiff = diff;
        behaviorKey = key;
        behaviorCurrent = currentAmount;
        behaviorPrevious = previousAmount;
      }
    }
    if (behaviorKey) {
      const label = categoryLabels.get(behaviorKey) ?? behaviorKey;
      const percentage = (behaviorDiff / behaviorPrevious) * 100;
      const contributorsMap = categoryDescriptionTotals.get(currentMonthKey)?.get(behaviorKey) ?? new Map();
      const topContributors = Array.from(contributorsMap.entries())
        .sort(([, a], [, b]) => (b as number) - (a as number))
        .slice(0, 3)
        .map(([desc, value]) => ({
          label: (desc as string).replace(/\b\w/g, (c) => c.toUpperCase()),
          value: round2(value as number),
        }));
      insights.push({
        id: "category-behavior-change",
        type: "expense",
        severity: percentage >= 30 ? "high" : "medium",
        title: "Mudança de comportamento detectada",
        message: `Seus gastos com ${label} aumentaram ${percentage.toFixed(0)}% em relação ao mês anterior.`,
        metric_label: "Categoria",
        metric_value: label,
        explanation: {
          current_period_label: "Este mês",
          previous_period_label: "Mês anterior",
          current_value: round2(behaviorCurrent),
          previous_value: round2(behaviorPrevious),
          difference: round2(behaviorDiff),
          percentage: Math.round(percentage * 10) / 10,
          top_contributors: topContributors,
        },
      });
    }
  }

  const recurringItems = Array.from(recurringAmounts.entries())
    .filter(([label]) => (recurringCounter.get(label) ?? 0) >= 2)
    .sort(([, a], [, b]) => b - a);
  if (recurringItems.length > 0) {
    const [recurringLabel, recurringTotal] = recurringItems[0];
    const count = recurringCounter.get(recurringLabel) ?? 0;
    const displayLabel = recurringLabel.replace(/\b\w/g, (c) => c.toUpperCase());
    insights.push({
      id: "recurring-expense",
      type: "expense",
      severity: "medium",
      title: "Despesa recorrente detectada",
      message: `'${displayLabel}' apareceu ${count} vezes e já consumiu R$ ${recurringTotal.toFixed(2)}.`,
      metric_label: "Recorrência",
      metric_value: String(count),
    });
  }

  if (currentIncomes > 0) {
    const fixedRatio = (currentExpenses / currentIncomes) * 100;
    insights.push({
      id: "cashflow-health",
      type: "cashflow",
      severity: fixedRatio >= 85 ? "high" : fixedRatio >= 70 ? "medium" : "low",
      title: "Pressão no fluxo de caixa",
      message: `Seus gastos consumiram ${fixedRatio.toFixed(0)}% da receita do mês. O saldo disponível atual é de R$ ${Math.max(currentIncomes - currentExpenses, 0).toFixed(2)}.`,
      metric_label: "Comprometimento",
      metric_value: `${fixedRatio.toFixed(0)}%`,
    });
  }

  if (previousIncomes > 0) {
    const incomeGrowth = ((currentIncomes - previousIncomes) / previousIncomes) * 100;
    insights.push({
      id: "income-trend",
      type: "income",
      severity: incomeGrowth >= 0 ? "low" : "medium",
      title: "Tendência de receitas",
      message: `As receitas variaram ${incomeGrowth.toFixed(1)}% em relação ao mês anterior.`,
      metric_label: "Receita atual",
      metric_value: `R$ ${currentIncomes.toFixed(2)}`,
    });
  }

  const availableMonthlySavings = Math.max(currentIncomes - currentExpenses, 0);
  const activeGoals = goals.filter((g) => !g.completed);
  if (activeGoals.length > 0) {
    const nextGoal = activeGoals.reduce((best, g) =>
      Math.max(g.target - g.current, 0) < Math.max(best.target - best.current, 0) ? g : best,
    );
    const missing = Math.max(nextGoal.target - nextGoal.current, 0);
    let message: string;
    let severity: "low" | "medium" | "high";
    let metricValue: string;
    if (availableMonthlySavings > 0) {
      const estimatedMonths = missing / availableMonthlySavings;
      message = `No ritmo atual, a meta '${nextGoal.goal_name}' pode ser concluída em aproximadamente ${Math.max(1, Math.round(estimatedMonths))} meses.`;
      severity = estimatedMonths <= 6 ? "low" : "medium";
      metricValue = `R$ ${availableMonthlySavings.toFixed(2)}/mês`;
    } else {
      message = `A meta '${nextGoal.goal_name}' está sem folga mensal disponível; há risco de atraso se o padrão atual continuar.`;
      severity = "high";
      metricValue = "Sem folga";
    }
    insights.push({
      id: "goal-forecast",
      type: "goal",
      severity,
      title: "Projeção de metas",
      message,
      metric_label: "Capacidade mensal",
      metric_value: metricValue,
    });
  }

  if (forecastExpenses > currentIncomes && currentIncomes > 0) {
    insights.push({
      id: "deficit-risk",
      type: "risk",
      severity: "high",
      title: "Risco de déficit",
      message: `Se o ritmo de saídas continuar, o mês pode fechar em R$ ${forecastExpenses.toFixed(2)} de despesas, acima da receita atual.`,
      metric_label: "Previsão",
      metric_value: `R$ ${forecastExpenses.toFixed(2)}`,
    });
  }

  // Resumo financeiro mensal — mesma regra do backend, funciona igual
  // no LocalStorage.
  const topCategoriesMonth = currentCategoryMap
    ? Array.from(currentCategoryMap.entries())
        .sort(([, a], [, b]) => b - a)
        .slice(0, 3)
        .map(([key, total]) => ({
          category: categoryLabels.get(key) ?? key,
          total: round2(total),
          percentage: currentExpenses > 0 ? Math.round((total / currentExpenses) * 1000) / 10 : 0,
        }))
    : [];
  const [currentYear, currentMonthNum] = currentMonthKey.split("-");
  const resumo_mensal: MonthlySummary = {
    month_label: `${MONTH_NAMES[parseInt(currentMonthNum, 10) - 1]}/${currentYear.slice(2)}`,
    incomes: round2(currentIncomes),
    expenses: round2(currentExpenses),
    balance: round2(currentIncomes - currentExpenses),
    top_categories: topCategoriesMonth,
    income_trend_percentage:
      previousIncomes > 0
        ? Math.round(((currentIncomes - previousIncomes) / previousIncomes) * 1000) / 10
        : 0,
    expense_trend_percentage: variacao_percentual,
  };

  return {
    alerta: insights.length > 0 ? insights[0].message : alerta,
    previsao_proximo_mes,
    economias_sugeridas,
    media_gastos,
    variacao_percentual,
    historico,
    insights: insights.slice(0, 6),
    resumo_mensal,
  };
}

function ensureDemoNotifications(userId: number): void {
  const existing = loadNotifications(userId);
  if (existing.length > 0) return;

  const now = new Date().toISOString();
  const demo: Notification[] = [
    {
      id: 1,
      title: "Bem-vindo ao Finance AI",
      description: "Modo local ativado — seus dados serão salvos neste navegador.",
      category: NotificationCategory.Sistema,
      priority: NotificationPriority.Normal,
      status: NotificationStatus.Unread,
      created_at: now,
      action_url: "/transactions",
    },
    {
      id: 2,
      title: "Dica: adicione sua primeira transação",
      description: "Toque no botão + para registrar receitas e despesas.",
      category: NotificationCategory.Lembretes,
      priority: NotificationPriority.Low,
      status: NotificationStatus.Unread,
      created_at: now,
    },
  ];
  saveNotifications(userId, demo);
}

const localStorageBackend = {
  // --- Auth ---
  async login(data: { email: string; password: string }): Promise<AuthSession> {
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []);
    const user = users.find((u) => u.email.toLowerCase() === data.email.toLowerCase());
    if (!user) throw new Error("Credenciais inválidas");

    const hashed = await sha256(`${data.password}${user.passwordSalt}`);
    if (hashed !== user.passwordHash) throw new Error("Credenciais inválidas");

    setCurrentLocalUserId(user.id);

    const profile: UserProfile = {
      id: user.id,
      name: user.name,
      email: user.email,
      created_at: user.createdAt,
    };

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + 30);

    ensureDemoNotifications(user.id);

    return {
      session_token: `local-${user.id}-${Date.now()}`,
      user: profile,
      expires_at: expiresAt.toISOString(),
    };
  },

  async register(data: {
    name: string;
    email: string;
    password: string;
  }): Promise<AuthSession> {
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []);
    if (users.some((u) => u.email.toLowerCase() === data.email.toLowerCase())) {
      throw new Error("E-mail já cadastrado");
    }

    const salt = generateSalt();
    const passwordHash = await sha256(`${data.password}${salt}`);
    const id = users.length > 0 ? Math.max(...users.map((u) => u.id)) + 1 : 1;

    const record: LocalUserRecord = {
      id,
      name: data.name,
      email: data.email,
      passwordHash,
      passwordSalt: salt,
      createdAt: new Date().toISOString(),
    };
    users.push(record);
    writeLs(LS_KEY_USERS, users);

    setCurrentLocalUserId(id);

    const profile: UserProfile = {
      id,
      name: data.name,
      email: data.email,
      created_at: record.createdAt,
    };

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + 30);

    ensureDemoNotifications(id);

    return {
      session_token: `local-${id}-${Date.now()}`,
      user: profile,
      expires_at: expiresAt.toISOString(),
    };
  },

  async logout(sessionToken: string): Promise<void> {
    void sessionToken;
    setCurrentLocalUserId(null);
  },

  async forgotPassword(email: string): Promise<void> {
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []);
    const exists = users.some((u) => u.email.toLowerCase() === email.toLowerCase());
    if (!exists) {
      throw new Error("E-mail não encontrado");
    }
    // Modo demo: só retorna sucesso sem enviar e-mail real
    await new Promise((r) => setTimeout(r, 300));
  },

  async getProfile(): Promise<UserProfile> {
    const userId = requireCurrentUserId();
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []);
    const user = users.find((u) => u.id === userId);
    if (!user) throw new Error("Usuário não encontrado");
    return {
      id: user.id,
      name: user.name,
      email: user.email,
      created_at: user.createdAt,
    };
  },

  async updateProfile(data: { name?: string; email?: string }): Promise<UserProfile> {
    const userId = requireCurrentUserId();
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []);
    const user = users.find((u) => u.id === userId);
    if (!user) throw new Error("Usuário não encontrado");
    if (data.name) user.name = data.name;
    if (data.email) user.email = data.email;
    writeLs(LS_KEY_USERS, users);
    return {
      id: user.id,
      name: user.name,
      email: user.email,
      created_at: user.createdAt,
    };
  },

  async deleteAccount(): Promise<void> {
    const userId = requireCurrentUserId();
    const users = readLs<LocalUserRecord[]>(LS_KEY_USERS, []).filter((u) => u.id !== userId);
    writeLs(LS_KEY_USERS, users);
    setCurrentLocalUserId(null);
  },

  async getSettings(): Promise<UserSettings> {
    const userId = requireCurrentUserId();
    const all = readLs<Record<number, UserSettings>>(LS_KEY_SETTINGS, {});
    return (
      all[userId] || {
        user_id: userId,
        currency: "BRL",
        locale: "pt-BR",
        theme: "dark",
        notifications_enabled: true,
        ai_enabled: true,
        updated_at: new Date().toISOString(),
      }
    );
  },

  async updateSettings(data: Partial<UserSettings>): Promise<UserSettings> {
    const userId = requireCurrentUserId();
    const all = readLs<Record<number, UserSettings>>(LS_KEY_SETTINGS, {});
    const current = all[userId] || {
      user_id: userId,
      currency: "BRL",
      locale: "pt-BR",
      theme: "dark",
      notifications_enabled: true,
      ai_enabled: true,
      updated_at: new Date().toISOString(),
    };
    const updated = { ...current, ...data, updated_at: new Date().toISOString() };
    all[userId] = updated;
    writeLs(LS_KEY_SETTINGS, all);
    return updated;
  },

  // --- Transactions ---
  async getTransactions(): Promise<Transaction[]> {
    const userId = requireCurrentUserId();
    return sortTransactionsByDateDesc(loadTransactions(userId));
  },

  async createTransaction(data: Partial<Transaction>): Promise<Transaction> {
    const userId = requireCurrentUserId();
    const list = loadTransactions(userId);
    const description = data.description ?? "Sem descrição";
    const amount = Number(data.amount) || 0;
    const type = data.type === "expense" ? "expense" : "income";
    const date = data.date ?? new Date().toISOString();
    const record: LocalTransactionRecord = {
      id: nextId(list),
      description,
      amount,
      type,
      category: data.category ?? "Outros",
      date,
      // Mesmo hash de deduplicação calculado pelo backend em toda
      // transação (manual ou importada) — permite que uma futura
      // importação reconheça esta transação como já existente.
      dedupe_hash: computeDedupeHash(date, normalizeDescription(description), amount, type),
    };
    list.push(record);
    saveTransactions(userId, list);
    return record;
  },

  async updateTransaction(
    id: number,
    data: Partial<Transaction>,
  ): Promise<Transaction> {
    const userId = requireCurrentUserId();
    const list = loadTransactions(userId);
    const idx = list.findIndex((t) => t.id === id);
    if (idx === -1) throw new Error("Transação não encontrada");
    list[idx] = {
      ...list[idx],
      ...data,
      id: list[idx].id,
    } as Transaction;
    saveTransactions(userId, list);
    return list[idx];
  },

  async deleteTransaction(id: number): Promise<void> {
    const userId = requireCurrentUserId();
    const list = loadTransactions(userId).filter((t) => t.id !== id);
    saveTransactions(userId, list);
  },

  // --- Goals ---
  async getGoalsStatus(): Promise<Goal[]> {
    const userId = requireCurrentUserId();
    return loadGoals(userId);
  },

  async createGoal(data: Partial<Goal> & { name?: string; target_amount?: number; current_amount?: number }): Promise<Goal> {
    const userId = requireCurrentUserId();
    const list = loadGoals(userId);
    const goalName = data.goal_name ?? data.name ?? "Nova Meta";
    const target = Number(data.target ?? data.target_amount) || 0;
    const current = Number(data.current ?? data.current_amount) || 0;

    const base: Omit<Goal, "missing" | "percent"> = {
      id: nextId(list),
      goal_name: goalName,
      target,
      current,
      deadline: data.deadline,
      completed: data.completed ?? false,
    };
    const record = computeGoalDerived(base);
    list.push(record);
    saveGoals(userId, list);
    return record;
  },

  async depositGoal(id: number, amount: number): Promise<Goal> {
    const userId = requireCurrentUserId();
    const list = loadGoals(userId);
    const idx = list.findIndex((g) => g.id === id);
    if (idx === -1) throw new Error("Meta não encontrada");
    const updated = computeGoalDerived({
      ...list[idx],
      current: (list[idx].current ?? 0) + Number(amount),
    });
    list[idx] = updated;
    saveGoals(userId, list);
    return updated;
  },

  async completeGoal(id: number): Promise<Goal> {
    const userId = requireCurrentUserId();
    const list = loadGoals(userId);
    const idx = list.findIndex((g) => g.id === id);
    if (idx === -1) throw new Error("Meta não encontrada");
    const updated = computeGoalDerived({
      ...list[idx],
      completed: true,
      current: list[idx].target,
    });
    list[idx] = updated;
    saveGoals(userId, list);
    return updated;
  },

  async deleteGoal(id: number): Promise<void> {
    const userId = requireCurrentUserId();
    const list = loadGoals(userId).filter((g) => g.id !== id);
    saveGoals(userId, list);
  },

  // --- Dashboard ---
  async getSummary(): Promise<DashboardSummary> {
    const userId = requireCurrentUserId();
    return computeDashboardSummary(loadTransactions(userId));
  },

  async getInsights(): Promise<InsightData | null> {
    const userId = requireCurrentUserId();
    const settingsByUser = readLs<Record<number, UserSettings>>(LS_KEY_SETTINGS, {});
    const aiEnabled = settingsByUser[userId]?.ai_enabled ?? true;
    if (!aiEnabled) {
      return {
        ai_enabled: false,
        alerta: "Os Insights de IA estão desativados nas suas Configurações.",
        previsao_proximo_mes: 0,
        economias_sugeridas: 0,
        media_gastos: 0,
        variacao_percentual: 0,
        historico: [],
        insights: [],
      };
    }
    const result = computeInsights(loadTransactions(userId), loadGoals(userId));
    return result ? { ...result, ai_enabled: true } : result;
  },

  async getChartData(): Promise<ChartDataPoint[]> {
    const userId = requireCurrentUserId();
    return computeChartData(loadTransactions(userId));
  },

  // --- Importação de extrato (CSV) ---
  async previewImport(file: File): Promise<ImportPreviewResponse> {
    const userId = requireCurrentUserId();

    const filename = file.name;
    const content = await readFileAsText(file);

    try {
      validateCsvFile(filename, content);
    } catch (err) {
      if (err instanceof FileValidationError) {
        throw new Error(err.message);
      }
      throw err;
    }

    const { parsed, issues } = parseCsv(content);
    if (parsed.length === 0 && issues.length === 0) {
      throw new Error("O arquivo está vazio.");
    }

    const batches = loadImportBatches(userId);
    const batchId = nextId(batches);

    const existingTransactions = loadTransactions(userId);
    const existingExternalIds = new Set(
      existingTransactions.map((t) => t.external_id).filter((v): v is string => !!v),
    );
    const existingHashes = new Set(
      existingTransactions.map((t) => t.dedupe_hash).filter((v): v is string => !!v),
    );

    const seenExternalIds = new Set<string>();
    const seenHashes = new Set<string>();

    const stagedRows: LocalStagedRow[] = [];
    let rowId = 1;

    for (const row of parsed) {
      const normalized = normalizeDescription(row.description);
      const rowHash = computeDedupeHash(row.date, normalized, row.amount, row.type);

      let isDuplicate: boolean;
      if (row.external_id) {
        isDuplicate = existingExternalIds.has(row.external_id) || seenExternalIds.has(row.external_id);
      } else {
        isDuplicate = existingHashes.has(rowHash) || seenHashes.has(rowHash);
      }

      const category = suggestCategory(row.description, normalized);

      stagedRows.push({
        id: rowId++,
        batch_id: batchId,
        date: row.date,
        date_iso: row.date,
        description: row.description,
        amount: row.amount,
        type: row.type,
        category,
        category_source: category ? "rule" : "none",
        status: isDuplicate ? "duplicated" : "new",
        error_reason: null,
        normalized_description: normalized,
        dedupe_hash: rowHash,
        external_id: row.external_id,
      });

      if (row.external_id) seenExternalIds.add(row.external_id);
      seenHashes.add(rowHash);
    }

    for (const issue of issues) {
      stagedRows.push({
        id: rowId++,
        batch_id: batchId,
        date: null,
        date_iso: null,
        description: (issue.raw || "(linha não interpretada)").slice(0, 120),
        amount: null,
        type: null,
        category: null,
        category_source: "none",
        status: "error",
        error_reason: issue.reason,
        normalized_description: null,
        dedupe_hash: null,
        external_id: null,
      });
    }

    const newCount = stagedRows.filter((r) => r.status === "new").length;
    const duplicatedCount = stagedRows.filter((r) => r.status === "duplicated").length;
    const errorCount = stagedRows.filter((r) => r.status === "error").length;

    batches.push({
      id: batchId,
      filename,
      source: "csv",
      status: "preview",
      total: stagedRows.length,
      new_count: newCount,
      duplicated_count: duplicatedCount,
      error_count: errorCount,
      imported_count: 0,
      created_at: new Date().toISOString(),
      completed_at: null,
    });
    saveImportBatches(userId, batches);

    const allStaged = loadStagedRows(userId).concat(stagedRows);
    saveStagedRows(userId, allStaged);

    return {
      batch_id: batchId,
      filename,
      source: "csv",
      total: stagedRows.length,
      new: newCount,
      duplicated: duplicatedCount,
      errors: errorCount,
      rows: stagedRows.map((r) => ({
        id: r.id,
        date: r.date,
        description: r.description,
        amount: r.amount,
        type: r.type,
        category: r.category,
        category_source: r.category_source,
        status: r.status,
        error_reason: r.error_reason,
      })),
    };
  },

  async confirmImport(batchId: number, rows: ImportConfirmRow[]): Promise<ImportConfirmResponse> {
    const userId = requireCurrentUserId();
    const batches = loadImportBatches(userId);
    const batch = batches.find((b) => b.id === batchId);
    if (!batch) throw new Error("Importação não encontrada");
    if (batch.status === "completed") throw new Error("Esta importação já foi confirmada");
    if (rows.length === 0) throw new Error("Nenhuma movimentação selecionada para importar");

    const allStaged = loadStagedRows(userId);
    const stagedForBatch = new Map(
      allStaged.filter((r) => r.batch_id === batchId).map((r) => [r.id, r]),
    );
    const overridesById = new Map(rows.map((r) => [r.staged_id, r]));

    const transactions = loadTransactions(userId);
    let imported = 0;
    let skipped = 0;

    for (const [stagedId, stagedRow] of stagedForBatch.entries()) {
      const override = overridesById.get(stagedId);
      if (!override) continue;
      if (stagedRow.status !== "new" && stagedRow.status !== "duplicated") {
        skipped += 1;
        continue;
      }

      const record: LocalTransactionRecord = {
        id: nextId(transactions),
        description: override.description,
        amount: stagedRow.amount ?? 0,
        type: (stagedRow.type ?? "expense") as "income" | "expense",
        category: formatCategoryLabel(override.category || "Sem categoria"),
        date: stagedRow.date ?? new Date().toISOString(),
        source: "import",
        external_id: stagedRow.external_id,
        dedupe_hash: stagedRow.dedupe_hash ?? undefined,
        import_batch_id: batchId,
        original_description: stagedRow.description,
      };
      transactions.push(record);
      imported += 1;
    }

    skipped += rows.length - stagedForBatch.size;

    if (imported === 0) {
      throw new Error("Nenhuma das movimentações selecionadas pode ser importada");
    }

    saveTransactions(userId, transactions);

    const batchIdx = batches.findIndex((b) => b.id === batchId);
    batches[batchIdx] = {
      ...batches[batchIdx],
      status: "completed",
      imported_count: imported,
      completed_at: new Date().toISOString(),
    };
    saveImportBatches(userId, batches);

    return { status: "success", batch_id: batchId, imported, skipped };
  },

  async getImportBatches(): Promise<ImportBatchSummary[]> {
    const userId = requireCurrentUserId();
    return [...loadImportBatches(userId)].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  },

  async resetDatabase(): Promise<void> {
    const userId = getCurrentLocalUserId();
    if (userId !== null) {
      saveTransactions(userId, []);
      saveGoals(userId, []);
      saveNotifications(userId, []);
      saveImportBatches(userId, []);
      saveStagedRows(userId, []);
    }
  },
};

export const localStorageNotificationsService: LocalNotificationsService = {
  async list(params): Promise<ListNotificationsResponse> {
    const userId = requireCurrentUserId();
    let items = loadNotifications(userId);

    if (params.status) {
      items = items.filter((n) => n.status === params.status);
    }
    if (params.category) {
      items = items.filter((n) => n.category === params.category);
    }
    if (params.priority) {
      items = items.filter((n) => n.priority === params.priority);
    }
    if (params.q) {
      const q = params.q.toLowerCase();
      items = items.filter(
        (n) =>
          n.title.toLowerCase().includes(q) ||
          (n.description ?? "").toLowerCase().includes(q),
      );
    }
    if (params.from) {
      const fromTs = new Date(params.from).getTime();
      items = items.filter((n) => new Date(n.created_at).getTime() >= fromTs);
    }
    if (params.to) {
      const toTs = new Date(params.to).getTime();
      items = items.filter((n) => new Date(n.created_at).getTime() <= toTs);
    }

    items = items.sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );

    const total = items.length;
    const page = Math.max(1, params.page ?? 1);
    const pageSize = params.page_size ?? 50;
    const start = (page - 1) * pageSize;
    const paged = items.slice(start, start + pageSize);

    return {
      items: paged,
      page,
      page_size: pageSize,
      total,
    };
  },

  async markAsRead(id: number): Promise<MarkNotificationAsReadResponse> {
    const userId = requireCurrentUserId();
    const items = loadNotifications(userId).map((n) =>
      n.id === id
        ? { ...n, status: NotificationStatus.Read as const, read_at: n.read_at ?? new Date().toISOString() }
        : n,
    );
    saveNotifications(userId, items);
    return { ok: true };
  },

  async markAllAsRead(
    filters: MarkAllNotificationsAsReadRequest,
  ): Promise<MarkAllNotificationsAsReadResponse> {
    const userId = requireCurrentUserId();
    const now = new Date().toISOString();
    const items = loadNotifications(userId).map((n) => {
      if (filters.q) {
        const q = filters.q.toLowerCase();
        const matches =
          n.title.toLowerCase().includes(q) ||
          (n.description ?? "").toLowerCase().includes(q);
        if (!matches) return n;
      }
      if (filters.category && n.category !== filters.category) return n;
      if (filters.priority && n.priority !== filters.priority) return n;
      if (filters.from) {
        const fromTs = new Date(filters.from).getTime();
        if (new Date(n.created_at).getTime() < fromTs) return n;
      }
      if (filters.to) {
        const toTs = new Date(filters.to).getTime();
        if (new Date(n.created_at).getTime() > toTs) return n;
      }
      return {
        ...n,
        status: NotificationStatus.Read as const,
        read_at: n.read_at ?? now,
      };
    });
    saveNotifications(userId, items);
    return { ok: true };
  },
};

export type { LocalNotificationsService };

export const localStorageApi = {
  request: async <T,>(
    path: string,
    options: RequestInit = {},
    params?: Record<string, unknown>,
  ): Promise<T> => {
    void path;
    void options;
    void params;
    throw new Error("storage.request não está disponível no modo local");
  },
  ...localStorageBackend,
};
