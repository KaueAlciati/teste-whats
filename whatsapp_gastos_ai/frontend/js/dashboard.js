document.addEventListener("DOMContentLoaded", async () => {
  if (!document.body.classList.contains("page-dashboard")) return;

  const state = {
    period: "current_month",
    user: null,
    summary: null,
    categoriesChart: null,
    cashFlowChart: null,
  };

  const summaryCopy = document.getElementById("dashboard-summary-copy");
  const periodBadge = document.getElementById("period-badge");
  const summaryCards = document.getElementById("summary-cards");
  const recentTransactions = document.getElementById("recent-transactions");
  const remindersList = document.getElementById("reminders-list");
  const aiSummary = document.getElementById("ai-summary");
  const goalsList = document.getElementById("goals-list");
  const categoriesCanvas = document.getElementById("categories-chart");
  const cashFlowCanvas = document.getElementById("cash-flow-chart");

  function renderMetricCard({ label, value, previous, comparison, tone = "neutral" }) {
    const delta = Number(comparison || 0);
    const deltaClass = delta >= 0 ? "summary-positive" : "summary-negative";
    const deltaLabel = previous !== undefined && previous !== null
      ? `<small class="${deltaClass}">${delta >= 0 ? "+" : ""}${delta.toFixed(1)}% vs período anterior</small>`
      : "";
    return `
      <article class="card summary-card">
        <div class="metric">
          <span class="metric-label">${window.FincontrolUtils.escapeHtml(label)}</span>
          <strong class="metric-value ${tone === "positive" ? "summary-positive" : tone === "negative" ? "summary-negative" : ""}">${window.FincontrolUtils.formatCurrency(value)}</strong>
          ${deltaLabel}
        </div>
      </article>
    `;
  }

  function renderSummary(summary) {
    if (!summary) return;
    const periodLabel = window.FincontrolUtils.getPeriodLabel(summary.period?.value || state.period);
    if (summaryCopy) summaryCopy.textContent = summary.ai_summary?.text || "Sem resumo disponível.";
    if (periodBadge) periodBadge.innerHTML = `<strong>${window.FincontrolUtils.escapeHtml(periodLabel)}</strong><span>${window.FincontrolUtils.escapeHtml(summary.period?.label || "")}</span>`;

    if (summaryCards) {
      summaryCards.innerHTML = [
        renderMetricCard({ label: "Saldo projetado", value: summary.cards?.balance?.value, comparison: summary.cards?.balance?.comparison, tone: summary.cards?.balance?.value >= 0 ? "positive" : "negative" }),
        renderMetricCard({ label: "Entradas", value: summary.cards?.income?.value, comparison: summary.cards?.income?.comparison, tone: "positive" }),
        renderMetricCard({ label: "Saídas", value: summary.cards?.expense?.value, comparison: summary.cards?.expense?.comparison, tone: "negative" }),
        renderMetricCard({ label: "Faturas pendentes", value: summary.cards?.pending_invoice?.value, comparison: 0, tone: "neutral" }),
      ].join("");
    }

    renderRecentTransactions(summary.recent_transactions || []);
    renderReminders(summary.reminders || []);
    renderGoals(summary.goals || []);
    renderAiSummary(summary.ai_summary || null);
    renderCharts(summary.charts || { categories: [], cash_flow: { labels: [], income: [], expense: [] } });
  }

  function renderRecentTransactions(items) {
    if (!recentTransactions) return;
    if (!items.length) {
      recentTransactions.innerHTML = `<div class="empty-state">Nenhuma movimentação encontrada para o período selecionado.</div>`;
      return;
    }

    recentTransactions.innerHTML = items.map((item) => `
      <div class="list-item">
        <strong>${window.FincontrolUtils.escapeHtml(item.description || "Movimentação")}</strong>
        <small>${window.FincontrolUtils.escapeHtml(item.category || "geral")} • ${window.FincontrolUtils.escapeHtml(item.payment_method || "não informado")} • ${window.FincontrolUtils.formatDate(item.date)}</small>
        <div class="meta-row">
          <span class="pill">${window.FincontrolUtils.escapeHtml(item.type || item.kind)}</span>
          <span class="pill">${window.FincontrolUtils.formatCurrency(item.amount)}</span>
        </div>
      </div>
    `).join("");
  }

  function renderReminders(items) {
    if (!remindersList) return;
    if (!items.length) {
      remindersList.innerHTML = `<div class="empty-state">Nenhum lembrete cadastrado.</div>`;
      return;
    }
    remindersList.innerHTML = items.map((item) => `
      <div class="list-item">
        <strong>${window.FincontrolUtils.escapeHtml(item.message || "Lembrete")}</strong>
        <small>Cron: ${window.FincontrolUtils.escapeHtml(item.cron || "-")} • Criado em ${window.FincontrolUtils.formatDate(item.created_at)}</small>
      </div>
    `).join("");
  }

  function renderGoals(items) {
    if (!goalsList) return;
    if (!items.length) {
      goalsList.innerHTML = `<div class="empty-state">Sem metas configuradas nesta etapa do projeto.</div>`;
      return;
    }
  }

  function renderAiSummary(summary) {
    if (!aiSummary) return;
    if (!summary) {
      aiSummary.innerHTML = `<div class="empty-state">Resumo indisponível.</div>`;
      return;
    }
    aiSummary.innerHTML = `
      <div class="list-item">
        <strong>${window.FincontrolUtils.escapeHtml(summary.title || "Resumo financeiro")}</strong>
        <p>${window.FincontrolUtils.escapeHtml(summary.text || "")}</p>
      </div>
      <div class="meta-row">
        ${(summary.highlights || []).map((line) => `<span class="pill">${window.FincontrolUtils.escapeHtml(line)}</span>`).join("")}
      </div>
    `;
  }

  function renderCharts(charts) {
    if (!window.Chart) return;

    if (state.categoriesChart) state.categoriesChart.destroy();
    if (state.cashFlowChart) state.cashFlowChart.destroy();

    const categoryData = charts.categories || [];
    state.categoriesChart = new Chart(categoriesCanvas, {
      type: "doughnut",
      data: {
        labels: categoryData.map((item) => item.label),
        datasets: [{
          data: categoryData.map((item) => item.value),
          backgroundColor: categoryData.map((item) => item.color || "#1b7a43"),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: "bottom" },
        },
      },
    });

    const cashFlow = charts.cash_flow || { labels: [], income: [], expense: [] };
    state.cashFlowChart = new Chart(cashFlowCanvas, {
      type: "bar",
      data: {
        labels: cashFlow.labels || [],
        datasets: [
          {
            label: "Entradas",
            data: cashFlow.income || [],
            backgroundColor: "rgba(27, 122, 67, 0.72)",
          },
          {
            label: "Saídas",
            data: cashFlow.expense || [],
            backgroundColor: "rgba(184, 50, 50, 0.72)",
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => window.FincontrolUtils.formatCurrency(value),
            },
          },
        },
        plugins: {
          legend: { position: "bottom" },
        },
      },
    });
  }

  async function loadData() {
    try {
      const summary = await window.FincontrolAPI.dashboardSummary(state.period);
      state.summary = summary;
      renderSummary(summary);
    } catch (error) {
      if (summaryCopy) summaryCopy.textContent = error.message || "Falha ao carregar o dashboard.";
      if (summaryCards) {
        summaryCards.innerHTML = `<div class="empty-state">Não foi possível carregar os dados do dashboard.</div>`;
      }
    }
  }

  async function init() {
    try {
      const me = await window.FincontrolAPI.me();
      state.user = me.user;
      await window.FincontrolLayout.renderShell(
        state.user,
        state.period,
        async (period) => {
          state.period = period;
          await loadData();
        },
        handleLogout,
      );
      bindPeriodChange();
      await loadData();
    } catch (error) {
      window.location.href = "/login";
    }
  }

  function bindPeriodChange() {
    const select = document.getElementById("period-select");
    if (!select) return;
    select.addEventListener("change", async (event) => {
      state.period = event.target.value;
      await loadData();
    });
  }

  async function handleLogout() {
    try {
      await window.FincontrolAPI.logout();
    } catch (_) {
      // ignore logout errors
    } finally {
      window.location.href = "/login";
    }
  }

  init();
});
