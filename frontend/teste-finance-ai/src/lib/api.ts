export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

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
    ? { ...headers, Authorization: `Bearer ${token}` }
    : headers;
}

export type Transaction = {
  id?: number;
  description: string;
  amount: number;
  type: "income" | "expense";
  category: string;
  date: string;
  /** "import" para transações vindas de importação de extrato (CSV/OFX);
      "manual" (ou ausente, em respostas antigas/modo local) para as
      demais. Nunca setado pelo cliente — só o backend atribui. */
  source?: "manual" | "import";
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

export type UserProfile = {
  id: number;
  name: string;
  email: string;
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
  expires_at: string;
};

export type ImportSourceFormat = "csv" | "ofx";
export type ImportRowStatus = "new" | "duplicated" | "error";

export type ImportPreviewRow = {
  id: number;
  date: string | null;
  description: string;
  amount: number | null;
  type: "income" | "expense" | null;
  category: string | null;
  category_source: "rule" | "none";
  status: ImportRowStatus;
  error_reason: string | null;
};

export type ImportPreviewResponse = {
  batch_id: number;
  filename: string;
  source: ImportSourceFormat;
  total: number;
  new: number;
  duplicated: number;
  errors: number;
  rows: ImportPreviewRow[];
};

export type ImportConfirmRow = {
  staged_id: number;
  category: string;
  description: string;
};

export type ImportConfirmResponse = {
  status: string;
  batch_id: number;
  imported: number;
  skipped: number;
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

  // Goals
  getGoalsStatus: async (): Promise<Goal[]> => {
    return await fetchWithTimeout(`${API_URL}/goals/status`);
  },

  createGoal: async (data: Partial<Goal>) => {
    return await fetchWithTimeout(`${API_URL}/goals`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  depositGoal: async (id: number, amount: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}/deposit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ amount }),
    });
  },

  completeGoal: async (id: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}/complete`, {
      method: "POST",
    });
  },

  deleteGoal: async (id: number) => {
    return await fetchWithTimeout(`${API_URL}/goals/${id}`, {
      method: "DELETE",
    });
  },

  // Dashboard
  getSummary: async (): Promise<DashboardSummary> => {
    return await fetchWithTimeout(`${API_URL}/dashboard-summary`);
  },

  // Insights
  getInsights: async (): Promise<InsightData | null> => {
    return await fetchWithTimeout(`${API_URL}/insights`);
  },

  // Charts
  getChartData: async (): Promise<ChartDataPoint[]> => {
    return await fetchWithTimeout(`${API_URL}/chart-data`);
  },

  // Authentication
  forgotPassword: async (email: string) => {
    return await fetchWithTimeout(`${API_URL}/auth/forgot-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
    });
  },

  login: async (data: { email: string; password: string }): Promise<AuthSession> => {
    return await fetchWithTimeout(`${API_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  register: async (data: { name: string; email: string; password: string }): Promise<AuthSession> => {
    return await fetchWithTimeout(`${API_URL}/auth/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });
  },

  logout: async (sessionToken: string) => {
    void sessionToken; // mantido na assinatura por compatibilidade de chamada
    return await fetchWithTimeout(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
  },

  getProfile: async (): Promise<UserProfile> => {
    return await fetchWithTimeout(`${API_URL}/auth/profile`, {
      method: "GET",
    });
  },

  updateProfile: async (data: { name?: string; email?: string }): Promise<UserProfile> => {
    return await fetchWithTimeout(`${API_URL}/auth/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },

  deleteAccount: async (): Promise<void> => {
    return await fetchWithTimeout(`${API_URL}/auth/account`, {
      method: "DELETE",
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

  // Importação de extrato (CSV/OFX)
  previewImport: async (file: File): Promise<ImportPreviewResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    // Sem Content-Type manual aqui: o navegador define o boundary do
    // multipart/form-data sozinho. Timeout maior que o padrão porque
    // parsing + deduplicação de um extrato grande pode levar mais
    // que os 10s usados pelas outras chamadas.
    return await fetchWithTimeout(
      `${API_URL}/transactions/import/preview`,
      { method: "POST", body: formData },
      30000,
    );
  },

  confirmImport: async (
    batchId: number,
    rows: ImportConfirmRow[],
  ): Promise<ImportConfirmResponse> => {
    return await fetchWithTimeout(`${API_URL}/transactions/import/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: batchId, rows }),
    });
  },

  getImportBatches: async (): Promise<ImportBatchSummary[]> => {
    return await fetchWithTimeout(`${API_URL}/transactions/import/batches`);
  },
};
