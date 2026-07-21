window.FincontrolAPI = (() => {
  const config = window.FINCONTROL_CONFIG || { apiBase: "/api" };

  async function request(path, options = {}) {
    const response = await fetch(`${config.apiBase}${path}`, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      const message = payload.message || `Erro HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload.data ?? payload;
  }

  function get(path) {
    return request(path, { method: "GET" });
  }

  function post(path, body = {}) {
    return request(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  return {
    request,
    get,
    post,
    login: (identifier, password, remember_me = false) => post("/auth/login", { identifier, password, remember_me }),
    refresh: () => post("/auth/refresh", {}),
    logout: () => post("/auth/logout", {}),
    me: () => get("/auth/me"),
    dashboardSummary: (period) => get(`/dashboard/summary${period ? `?period=${encodeURIComponent(period)}` : ""}`),
    dashboardCategories: (period) => get(`/dashboard/categories${period ? `?period=${encodeURIComponent(period)}` : ""}`),
    dashboardCashFlow: (period) => get(`/dashboard/cash-flow${period ? `?period=${encodeURIComponent(period)}` : ""}`),
    dashboardRecentTransactions: (period) => get(`/dashboard/recent-transactions${period ? `?period=${encodeURIComponent(period)}` : ""}`),
    dashboardAiSummary: (period) => get(`/dashboard/ai-summary${period ? `?period=${encodeURIComponent(period)}` : ""}`),
  };
})();
