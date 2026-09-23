export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
).replace(/\/+$/, "");

const SESSION_STORAGE_KEY = "financeai_session";

/* Lê o token de sessão direto do localStorage (mesma chave usada pelo
   AuthContext). Fica aqui, e não como argumento de cada função, porque
   api.ts é um módulo comum — sem acesso ao React Context — e assim
   toda chamada autenticada ganha o header automaticamente, sem
   precisar que cada tela se lembre de passar o token na mão. */
function getStoredSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { session_token?: string };
    return parsed?.session_token || null;
  } catch {
    return null;
  }
}

function withAuthHeaders(headers: HeadersInit = {}): HeadersInit {
  const token = getStoredSessionToken();
  return token
    ? { Authorization: `Bearer ${token}`, ...headers }
    : headers;
}

export type Transaction = {
  id?: number;
  description: string;
  amount: number;
  type: "income" | "expense";
  category: string;
  date: string;
  has_attachment?: boolean;
  source?:
    | "manual"
    | "import"
    | "import_csv"
    | "import_pdf"
    | "import_image"
    | "dashboard_manual"
    | "web"
    | "whatsapp_text"
    | "whatsapp_audio"
    | "whatsapp_image"
    | "whatsapp_document";
};

export type Goal = {
  id: number;
  goal_name: string;
  target: number;
  current: number;
  missing: number;
  percent: number;
  deadline?: string;
  completed: boolean;
};

export type GoalWriteData = {
  name: string;
  target_amount: number;
  target_date?: string | null;
};

export type GoalStatus = "active" | "completed" | "all";

export type InsightEntry = {
  id: string;
  type: "expense" | "income" | "cashflow" | "goal" | "risk" | "opportunity";
  severity: "low" | "medium" | "high";
  title: string;
  message: string;
  metric_label?: string;
  metric_value?: string;
  /** Explicabilidade (de onde vem o número), quando o insight tiver. */
  explanation?: {
    current_period_label: string;
    previous_period_label: string;
    current_value: number;
    previous_value: number;
    difference: number;
    percentage: number;
    top_contributors: { label: string; value: number }[];
  };
};

export type MonthlySummary = {
  month_label: string;
  incomes: number;
  expenses: number;
  balance: number;
  top_categories: { category: string; total: number; percentage: number }[];
  income_trend_percentage: number;
  expense_trend_percentage: number;
};

export type InsightData = {
  /** false quando o usuário desligou "Insights Semanais da IA" em
      Configurações — nesse caso os demais campos vêm zerados/vazios
      e a tela deve mostrar um estado próprio, não tratar como "sem
      dados ainda". Ausente (undefined) em respostas antigas/modo
      local antes desta função existir — trate como true. */
  ai_enabled?: boolean;
  alerta: string;
  previsao_proximo_mes: number;
  economias_sugeridas: number;
  media_gastos: number;
  variacao_percentual: number;
  historico: {
    mes: string;
    valor: number;
  }[];
  insights: InsightEntry[];
  /** Resumo consolidado do mês atual — ausente quando não há dados suficientes. */
  resumo_mensal?: MonthlySummary | null;
};

export type FinancialProfileInput = {
  main_goal:
    | "emergency_reserve"
    | "pay_debts"
    | "purchase_goal"
    | "organize_finances"
    | "invest_future"
    | "grow_wealth";
  investment_horizon:
    | "up_to_6_months"
    | "up_to_1_year"
    | "one_to_three_years"
    | "three_to_five_years"
    | "more_than_five_years";
  risk_profile: "conservative" | "moderate" | "aggressive";
  liquidity_need: "high" | "medium" | "low";
  has_debts: boolean;
  income_type: "fixed" | "variable" | "mixed";
  main_priority:
    | "reduce_expenses"
    | "organize_budget"
    | "achieve_goals"
    | "start_investing"
    | "increase_savings";
};

export type FinancialProfile = FinancialProfileInput & {
  id: number;
  onboarding_completed: boolean;
  created_at: string;
  updated_at: string;
};

export type FinancialProfileState = {
  onboarding_completed: boolean;
  profile: FinancialProfile | null;
};

export type CategoryAmount = {
  category: string;
  amount: number;
  percentage: number;
};

export type GoalAnalysis = {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  remaining_amount: number;
  progress_percentage: number;
  target_date: string | null;
  required_monthly_amount: number | null;
};

export type InsightsAnalysis = {
  generated_at: string;
  profile: FinancialProfile;
  summary: {
    balance: number;
    current_month_income: number;
    current_month_expenses: number;
    free_amount: number;
    committed_income_percentage: number | null;
    average_monthly_expenses: number | null;
    average_monthly_income: number | null;
    transaction_count: number;
    largest_expense: {
      description: string;
      amount: number;
      category: string;
      transaction_date: string;
    } | null;
    top_expense_category: string | null;
    category_distribution: CategoryAmount[];
    previous_month_expenses: number;
    expense_change_percentage: number | null;
    category_changes: {
      category: string;
      current_amount: number;
      previous_amount: number;
      difference: number;
      percentage_change: number | null;
      direction: "increased" | "decreased" | "stable";
    }[];
    recent_expense_trend: "increasing" | "decreasing" | "stable" | null;
    monthly_history: { month: string; income: number; expense: number }[];
    active_goals_count: number;
    total_saved_in_goals: number;
    total_remaining_in_goals: number;
    goals: GoalAnalysis[];
    average_goal_contribution: number | null;
    estimated_monthly_savings_capacity: number | null;
  };
  health: {
    level: "good" | "attention" | "critical";
    score: number;
    explanation: string;
  };
  alerts: {
    code: string;
    severity: "positive" | "attention" | "critical" | "info";
    title: string;
    message: string;
  }[];
  possibilities: {
    title: string;
    objective: string;
    horizon: string;
    liquidity: string;
    risk: string;
    care: string;
  }[];
  ai: {
    available: boolean;
    cached: boolean;
    generated_at: string | null;
    message: string | null;
    content: {
      financial_summary: string;
      positive_points: string[];
      attention_points: string[];
      improvements: string[];
      cut_suggestions: string[];
      prioritization: string;
      goals_analysis: string;
      next_steps: string[];
    } | null;
  };
  market: {
    available: boolean;
    message: string;
    updated_at: string | null;
    cached: boolean;
    selic: MarketRateIndicator;
    cdi: MarketRateIndicator;
    ipca: MarketRateIndicator;
    savings: MarketRateIndicator;
    treasury_selic: {
      status: "available" | "unavailable";
      title: string | null;
      maturity_date: string | null;
      rate: number | null;
      unit: string;
      reference_period: string | null;
      source: MarketSource;
      message: string | null;
    };
  };
};

type MarketSource = {
  name: string;
  url: string;
};

type MarketRateIndicator = {
  status: "available" | "unavailable";
  value: number | null;
  unit: string;
  reference_period: string | null;
  source: MarketSource;
  message: string | null;
};

export type DashboardInsight = {
  onboarding_completed: boolean;
  short_insight: string;
};

export type DashboardSummary = {
  incomes: number;
  expenses: number;
  total: number;
  balance_trend_percentage: number;
  income_trend_percentage: number;
  expense_trend_percentage: number;
  expense_ratio: number;
};

export type ChartDataPoint = {
  name: string;
  income: number;
  expense: number;
};

export type DashboardData = {
  balance: number;
  total_income: number;
  total_expense: number;
  monthly_flow: ChartDataPoint[];
  recent_transactions: Transaction[];
};

export type UserProfile = {
  id: number;
  name: string;
  email: string;
  whatsapp_phone?: string;
  whatsapp_verified?: boolean;
  active?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type UserSettings = {
  user_id: number;
  currency: string;
  locale: string;
  theme: string;
  notifications_enabled: boolean;
  ai_enabled: boolean;
  updated_at: string;
};

export type AuthSession = {
  session_token: string;
  user: UserProfile;
  expires_at?: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: "bearer";
};

export type ImportSourceFormat = "csv" | "pdf" | "image";
export type ImportRowStatus =
  | "ready"
  | "possible_duplicate"
  | "needs_review"
  | "invalid"
  | "new"
  | "duplicated"
  | "error";

export type ImportColumnMapping = {
  date_column: string;
  description_column: string;
  amount_column?: string | null;
  type_column?: string | null;
  credit_column?: string | null;
  debit_column?: string | null;
};

export type ImportPreviewRow = {
  id: number;
  line_number?: number;
  date: string | null;
  description: string;
  amount: number | null;
  type: "income" | "expense" | null;
  category: string | null;
  category_source: "rule" | "fallback" | "none";
  status: ImportRowStatus;
  error_reason: string | null;
};

export type ImportPreviewResponse = {
  batch_id?: number;
  filename: string;
  source: ImportSourceFormat;
  delimiter?: "," | ";";
  columns?: string[];
  mapping_required?: boolean;
  mapping?: ImportColumnMapping | null;
  sample_rows?: Array<Record<string, string>>;
  total: number;
  ready?: number;
  possible_duplicates?: number;
  needs_review?: number;
  invalid?: number;
  new?: number;
  duplicated?: number;
  errors?: number;
  rows: ImportPreviewRow[];
};

export type ImportConfirmRow = {
  staged_id?: number;
  date?: string;
  amount?: number;
  type?: "income" | "expense";
  category?: string;
  description: string;
  allow_duplicate?: boolean;
};

export type ImportConfirmResponse = {
  status: string;
  batch_id?: number;
  imported: number;
  skipped?: number;
  skipped_duplicates?: number;
};

export type ImportBatchSummary = {
  id: number;
  filename: string;
  source: ImportSourceFormat;
  status: "processing" | "preview" | "completed" | "failed" | "cancelled";
  total: number;
  new_count: number;
  duplicated_count: number;
  error_count: number;
  imported_count: number;
  created_at: string;
  completed_at?: string | null;
};

export type HttpErrorKind =
  | "network_unavailable"
  | "timeout"
  | "http_4xx"
  | "http_5xx"
  | "unknown";

export class HttpError extends Error {
  readonly kind: HttpErrorKind;
  readonly status?: number;
  readonly responseBody?: unknown;

  constructor(
    message: string,
    kind: HttpErrorKind,
    status?: number,
    responseBody?: unknown,
  ) {
    super(message);
    this.name = "HttpError";
    this.kind = kind;
    this.status = status;
    this.responseBody = responseBody;
  }
}

export function isBackendUnavailableError(error: unknown): boolean {
  if (!(error instanceof HttpError)) {
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      return true;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      return true;
    }
    return false;
  }
  return (
    error.kind === "network_unavailable" ||
    error.kind === "timeout" ||
    error.kind === "http_5xx"
  );
}

export function isAuthOrValidationError(error: unknown): boolean {
  if (!(error instanceof HttpError)) return false;
  return error.kind === "http_4xx";
}

const fetchWithTimeout = async (
  url: string,
  options: RequestInit = {},
  timeout = 10000,
) => {
  const controller = new AbortController();

  const id = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      headers: withAuthHeaders(options.headers),
      signal: controller.signal,
    });

    clearTimeout(id);

    if (!response.ok) {
      let responseBody: unknown = undefined;
      try {
        responseBody = await response.json();
      } catch {
        // ignore parse errors for error bodies
      }

      const kind: HttpErrorKind =
        response.status >= 500 ? "http_5xx" : "http_4xx";

      throw new HttpError(
        `HTTP error! status: ${response.status}`,
        kind,
        response.status,
        responseBody,
      );
    }

    return await response.json();
  } catch (error) {
    clearTimeout(id);

    console.error(`Fetch error on ${url}:`, error);

    if (error instanceof HttpError) throw error;

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new HttpError(
        `Request timed out: ${url}`,
        "timeout",
        undefined,
        undefined,
      );
    }

    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new HttpError(
        `Backend unavailable: ${url}`,
        "network_unavailable",
        undefined,
        undefined,
      );
    }

    throw new HttpError(
      error instanceof Error ? error.message : "Unknown fetch error",
      "unknown",
      undefined,
      undefined,
    );
  }
};

const fetchFileWithTimeout = async (
  url: string,
  timeout = 30000,
): Promise<{ blob: Blob; filename: string }> => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: withAuthHeaders(),
      signal: controller.signal,
    });
    clearTimeout(id);

    if (!response.ok) {
      let responseBody: unknown;
      try {
        responseBody = await response.json();
      } catch {
        responseBody = undefined;
      }
      throw new HttpError(
        `HTTP error! status: ${response.status}`,
        response.status >= 500 ? "http_5xx" : "http_4xx",
        response.status,
        responseBody,
      );
    }

    const disposition = response.headers.get("content-disposition") ?? "";
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
    const defaultExtension = response.headers
      .get("content-type")
      ?.includes("text/csv")
      ? "csv"
      : "xlsx";
    return {
      blob: await response.blob(),
      filename:
        filenameMatch?.[1] ?? `extrato-fincontrol.${defaultExtension}`,
    };
  } catch (error) {
    clearTimeout(id);
    if (error instanceof HttpError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new HttpError("Export request timed out", "timeout");
    }
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new HttpError("Backend unavailable", "network_unavailable");
    }
    throw new HttpError(
      error instanceof Error ? error.message : "Unknown export error",
      "unknown",
    );
  }
};

export const api = {
  request: async <T,>(
    path: string,
    options: RequestInit = {},
    params?: Record<string, unknown>,
  ): Promise<T> => {
    let url = `${API_URL}${path}`;

    if (params && options.method === "GET") {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    const requestOptions: RequestInit = {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    };

    if (params && options.method !== "GET") {
      requestOptions.body = JSON.stringify(params);
    }

    return await fetchWithTimeout(url, requestOptions);
  },

  // Utility
  resetDatabase: () =>
    fetchWithTimeout(`${API_URL}/reset`, {
      method: "DELETE",
    }),
  // Transactions

  getTransactions: async (): Promise<Transaction[]> => {
    return await fetchWithTimeout(`${API_URL}/transactions`);
  },

  createTransaction: async (data: Partial<Transaction>) => {
    return await fetchWithTimeout(`${API_URL}/transactions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  updateTransaction: async (id: number, data: Partial<Transaction>) => {
    return await fetchWithTimeout(`${API_URL}/transactions/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  deleteTransaction: async (id: number) => {
    return await fetchWithTimeout(`${API_URL}/transactions/${id}`, {
      method: "DELETE",
    });
  },

  getTransactionAttachment: async (id: number): Promise<Blob> => {
    const response = await fetchFileWithTimeout(
      `${API_URL}/transactions/${id}/attachment`,
    );
    return response.blob;
  },

  exportTransactions: async (options: {
    format?: "xlsx" | "csv";
    startDate?: string;
    endDate?: string;
  }): Promise<{ blob: Blob; filename: string }> => {
    const params = new URLSearchParams({ format: options.format ?? "xlsx" });
    if (options.startDate) params.set("start_date", options.startDate);
    if (options.endDate) params.set("end_date", options.endDate);
    return await fetchFileWithTimeout(
      `${API_URL}/transactions/export?${params.toString()}`,
    );
  },

  // Goals
  getGoalsStatus: async (): Promise<Goal[]> => {
    return await fetchWithTimeout(`${API_URL}/goals`);
  },

  createGoal: async (data: GoalWriteData) => {
    return await fetchWithTimeout(`${API_URL}/goals`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  updateGoal: async (id: number, data: Partial<GoalWriteData>) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  depositGoal: async (id: number, amount: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ current_amount_delta: amount }),
    });
  },

  completeGoal: async (id: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status: "completed" }),
    });
  },

  deleteGoal: async (id: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}`, {
      method: "DELETE",
    });
  },

  // Dashboard
  getDashboard: async (): Promise<DashboardData> => {
    return await fetchWithTimeout(`${API_URL}/dashboard`);
  },

  getSummary: async (): Promise<DashboardSummary> => {
    return await fetchWithTimeout(`${API_URL}/dashboard-summary`);
  },

  // Insights
  getInsights: async (): Promise<InsightData | null> => {
    return await fetchWithTimeout(`${API_URL}/insights`);
  },

  getFinancialProfile: async (): Promise<FinancialProfileState> => {
    return await fetchWithTimeout(`${API_URL}/insights/profile`);
  },

  createFinancialProfile: async (
    data: FinancialProfileInput,
  ): Promise<FinancialProfile> => {
    return await fetchWithTimeout(`${API_URL}/insights/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  updateFinancialProfile: async (
    data: FinancialProfileInput,
  ): Promise<FinancialProfile> => {
    return await fetchWithTimeout(`${API_URL}/insights/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  getInsightsAnalysis: async (): Promise<InsightsAnalysis> => {
    return await fetchWithTimeout(`${API_URL}/insights`);
  },

  refreshInsightsAnalysis: async (): Promise<InsightsAnalysis> => {
    return await fetchWithTimeout(`${API_URL}/insights/refresh`, {
      method: "POST",
    });
  },

  getDashboardInsight: async (): Promise<DashboardInsight> => {
    return await fetchWithTimeout(`${API_URL}/insights/summary`);
  },

  // Charts
  getChartData: async (): Promise<ChartDataPoint[]> => {
    return await fetchWithTimeout(`${API_URL}/chart-data`);
  },

  // Authentication
  forgotPassword: async (email: string): Promise<{ message: string }> => {
    return await fetchWithTimeout(`${API_URL}/auth/forgot-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
    });
  },

  resetPassword: async (data: {
    token: string;
    new_password: string;
    confirm_new_password: string;
  }): Promise<{ status: string }> => {
    return await fetchWithTimeout(`${API_URL}/auth/reset-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  login: async (data: { email: string; password: string }): Promise<AuthTokenResponse> => {
    return await fetchWithTimeout(`${API_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  register: async (data: {
    name: string;
    email: string;
    whatsapp_phone: string;
    password: string;
  }): Promise<UserProfile> => {
    return await fetchWithTimeout(`${API_URL}/auth/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  getMe: async (accessToken: string): Promise<UserProfile> => {
    return await fetchWithTimeout(`${API_URL}/auth/me`, {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  },

  updateProfile: async (data: { name?: string; email?: string }): Promise<UserProfile> => {
    return await fetchWithTimeout(`${API_URL}/auth/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  changePassword: async (data: {
    current_password: string;
    new_password: string;
    confirm_new_password: string;
  }): Promise<{ status: string }> => {
    return await fetchWithTimeout(`${API_URL}/auth/change-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  clearFinancialHistory: async (
    confirmation: string,
  ): Promise<{ status: string }> => {
    return await fetchWithTimeout(`${API_URL}/auth/financial-history`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation }),
    });
  },

  deleteAccount: async (confirmation: string): Promise<{ status: string }> => {
    return await fetchWithTimeout(`${API_URL}/auth/account`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation }),
    });
  },

  getSettings: async (): Promise<UserSettings> => {
    return await fetchWithTimeout(`${API_URL}/settings`, {
      method: "GET",
    });
  },

  updateSettings: async (data: Partial<UserSettings>): Promise<UserSettings> => {
    return await fetchWithTimeout(`${API_URL}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  // Importação de extrato CSV: a prévia não persiste dados.
  previewImport: async (
    file: File,
    mapping?: ImportColumnMapping,
  ): Promise<ImportPreviewResponse> => {
    if (file.size > 10 * 1024 * 1024) {
      throw new Error("O arquivo excede o limite de 10 MB.");
    }
    const isCsv = file.name.toLowerCase().endsWith(".csv");
    const content = isCsv ? await file.text() : undefined;
    const contentBase64 = isCsv ? undefined : await fileToBase64(file);
    // Timeout maior que o padrão porque análise e deduplicação de um
    // extrato grande podem levar mais que as demais chamadas.
    return await fetchWithTimeout(
      `${API_URL}/transactions/import/preview`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content,
          content_base64: contentBase64,
          mime_type: file.type || undefined,
          mapping: isCsv ? mapping : undefined,
        }),
      },
      90000,
    );
  },

  confirmImport: async (
    rows: ImportConfirmRow[],
    source: ImportSourceFormat = "csv",
    attachmentFile?: File,
  ): Promise<ImportConfirmResponse> => {
    const attachment = attachmentFile
      ? {
          filename: attachmentFile.name,
          content_base64: await fileToBase64(attachmentFile),
          mime_type: attachmentFile.type || undefined,
        }
      : undefined;
    return await fetchWithTimeout(`${API_URL}/transactions/import/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source,
        attachment,
        rows: rows.map((row) => ({
          date: row.date,
          amount: row.amount,
          type: row.type,
          category: row.category,
          description: row.description,
          allow_duplicate: row.allow_duplicate ?? false,
        })),
      }),
    });
  },

  getImportBatches: async (): Promise<ImportBatchSummary[]> => {
    return await fetchWithTimeout(`${API_URL}/transactions/import/batches`);
  },
};


function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Não foi possível ler o arquivo."));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string" || !result.includes(",")) {
        reject(new Error("Conteúdo do arquivo inválido."));
        return;
      }
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}
