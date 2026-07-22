document.addEventListener("DOMContentLoaded", async () => {
  if (!document.body.classList.contains("page-dashboard") || !document.getElementById("summary-cards")) return;

  const state = { period: "current_month", user: null, summary: null, categoriesChart: null, cashFlowChart: null };
  const summaryCopy = document.getElementById("dashboard-summary-copy");
  const periodBadge = document.getElementById("period-badge");
  const summaryCards = document.getElementById("summary-cards");
  const recentTransactions = document.getElementById("recent-transactions");
  const remindersList = document.getElementById("reminders-list");
  const aiSummary = document.getElementById("ai-summary");
  const goalsList = document.getElementById("goals-list");
  const categoriesCanvas = document.getElementById("categories-chart");
  const cashFlowCanvas = document.getElementById("cash-flow-chart");

  function renderMetricCard({ label, value, previous, comparison, tone = "neutral", lucide }) {
    const delta = Number(comparison || 0);
    const deltaClass = tone === "negative" ? "summary-negative" : delta >= 0 ? "summary-positive" : "summary-negative";
    const deltaLabel = previous !== undefined && previous !== null ? `<small class="${deltaClass}">${delta >= 0 ? "+" : ""}${delta.toFixed(1)}% vs período anterior</small>` : `<small>Período selecionado</small>`;
    return `<div class="col-md-6 col-xl-3 mb-4"><article class="card shadow h-100 summary-card"><div class="card-body"><div class="d-flex align-items-center justify-content-between"><span class="metric-label">${window.FincontrolUtils.escapeHtml(label)}</span><span class="metric-icon ${tone === "negative" ? "metric-icon-danger" : ""}"><i data-lucide="${lucide}" aria-hidden="true"></i></span></div><strong class="metric-value d-block mt-2 ${tone === "positive" ? "summary-positive" : tone === "negative" ? "summary-negative" : ""}">${window.FincontrolUtils.formatCurrency(value)}</strong>${deltaLabel}</div></article></div>`;
  }

  function renderSummary(summary) {
    if (!summary) return;
    const periodLabel = window.FincontrolUtils.getPeriodLabel(summary.period?.value || state.period);
    if (summaryCopy) summaryCopy.textContent = summary.ai_summary?.text || "Visão geral das suas movimentações no período selecionado.";
    if (periodBadge) periodBadge.innerHTML = `<strong>${window.FincontrolUtils.escapeHtml(periodLabel)}</strong><small>${window.FincontrolUtils.escapeHtml(summary.period?.label || "Dados atualizados")}</small>`;
    if (summaryCards) summaryCards.innerHTML = [
      renderMetricCard({ label: "Saldo atual", value: summary.cards?.balance?.value, comparison: summary.cards?.balance?.comparison, tone: summary.cards?.balance?.value >= 0 ? "positive" : "negative", lucide: "wallet" }),
      renderMetricCard({ label: "Entradas", value: summary.cards?.income?.value, comparison: summary.cards?.income?.comparison, tone: "positive", lucide: "arrow-down-left" }),
      renderMetricCard({ label: "Saídas", value: summary.cards?.expense?.value, comparison: summary.cards?.expense?.comparison, tone: "negative", lucide: "arrow-up-right" }),
      renderMetricCard({ label: "Faturas pendentes", value: summary.cards?.pending_invoice?.value, comparison: null, tone: "neutral", lucide: "receipt" }),
    ].join("");
    renderRecentTransactions(summary.recent_transactions || []);
    renderReminders(summary.reminders || []);
    renderGoals(summary.goals || []);
    renderAiSummary(summary.ai_summary || null);
    renderCharts(summary.charts || { categories: [], cash_flow: { labels: [], income: [], expense: [] } });
    window.lucide?.createIcons?.();
  }

  function renderRecentTransactions(items) {
    if (!recentTransactions) return;
    recentTransactions.innerHTML = items.length ? items.slice(0, 5).map((item) => `<div class="list-item"><div class="item-row"><span class="item-title"><span class="movement-dot ${String(item.type || item.kind).toLowerCase().includes("income") ? "is-income" : ""}"></span>${window.FincontrolUtils.escapeHtml(item.description || "Movimentação")}</span><strong class="${String(item.type || item.kind).toLowerCase().includes("income") ? "summary-positive" : "summary-negative"}">${window.FincontrolUtils.formatCurrency(item.amount)}</strong></div><small>${window.FincontrolUtils.escapeHtml(item.category || "Geral")} · ${window.FincontrolUtils.escapeHtml(item.payment_method || "Não informado")} · ${window.FincontrolUtils.formatDate(item.date)}</small></div>`).join("") : `<div class="empty-state">Nenhuma movimentação neste período.</div>`;
  }

  function renderReminders(items) {
    if (!remindersList) return;
    remindersList.innerHTML = items.length ? items.slice(0, 4).map((item) => `<div class="list-item"><div class="item-row"><span class="item-title"><span class="reminder-icon"><i data-lucide="bell" aria-hidden="true"></i></span>${window.FincontrolUtils.escapeHtml(item.message || "Lembrete")}</span><span class="status-label">Pendente</span></div><small>${window.FincontrolUtils.escapeHtml(item.cron || "Agendado")} · ${window.FincontrolUtils.formatDate(item.created_at)}</small></div>`).join("") : `<div class="empty-state">Nenhum lembrete cadastrado.</div>`;
  }

  function renderGoals(items) {
    if (!goalsList) return;
    goalsList.innerHTML = items.length ? items.slice(0, 3).map((item) => { const progress = Math.min(100, Math.max(0, Number(item.progress || item.percentage || 0))); return `<div class="list-item"><div class="item-row"><strong>${window.FincontrolUtils.escapeHtml(item.name || item.title || "Meta")}</strong><span class="status-label">${progress.toFixed(0)}%</span></div><div class="progress-track"><span style="width:${progress}%"></span></div><small>${window.FincontrolUtils.formatCurrency(item.current_value || item.current || 0)} de ${window.FincontrolUtils.formatCurrency(item.target_value || item.target || 0)}</small></div>`; }).join("") : `<div class="empty-state">Você ainda não possui metas.</div>`;
  }

  function renderAiSummary(summary) {
    if (!aiSummary) return;
    const content = aiSummary.querySelector(".ai-summary-content");
    if (content) content.innerHTML = `<p>${window.FincontrolUtils.escapeHtml(summary?.text || "Ainda não há dados suficientes para uma análise neste período.")}</p>`;
  }

  function renderCharts(charts) {
    if (!window.Chart || !categoriesCanvas || !cashFlowCanvas) return;
    state.categoriesChart?.destroy(); state.cashFlowChart?.destroy();
    const categories = charts.categories || [];
    const cashFlow = charts.cash_flow || { labels: [], income: [], expense: [] };
    const hasCategories = categories.some((item) => Number(item.value) > 0);
    const hasCashFlow = (cashFlow.labels || []).length > 0 && [...(cashFlow.income || []), ...(cashFlow.expense || [])].some((item) => Number(item) !== 0);
    document.getElementById("categories-empty")?.toggleAttribute("hidden", hasCategories);
    document.getElementById("cash-flow-empty")?.toggleAttribute("hidden", hasCashFlow);
    if (!hasCategories) categoriesCanvas.style.display = "none"; else categoriesCanvas.style.display = "block";
    if (!hasCashFlow) cashFlowCanvas.style.display = "none"; else cashFlowCanvas.style.display = "block";
    if (hasCategories) state.categoriesChart = new Chart(categoriesCanvas, { type: "doughnut", data: { labels: categories.map((item) => item.label), datasets: [{ data: categories.map((item) => item.value), backgroundColor: categories.map((item, index) => item.color || ["#15803D", "#22C55E", "#4ADE80", "#86EFAC", "#F59E0B", "#2563EB", "#7C3AED"][index % 7]), borderWidth: 3, borderColor: "#FFFFFF" }] }, options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 16, font: { family: "Inter" } } }, tooltip: { callbacks: { label: (context) => `${context.label}: ${window.FincontrolUtils.formatCurrency(context.raw)}` } } } } });
    if (hasCashFlow) state.cashFlowChart = new Chart(cashFlowCanvas, { type: "bar", data: { labels: cashFlow.labels || [], datasets: [{ label: "Entradas", data: cashFlow.income || [], backgroundColor: "#16A34A", borderRadius: 4, borderSkipped: false }, { label: "Saídas", data: cashFlow.expense || [], backgroundColor: "#DC2626", borderRadius: 4, borderSkipped: false }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false }, ticks: { color: "#6B7280", font: { family: "Inter" } } }, y: { beginAtZero: true, border: { display: false }, grid: { color: "#E5E7EB" }, ticks: { color: "#94A3B8", callback: (value) => window.FincontrolUtils.formatCurrency(value) } } }, plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 16, font: { family: "Inter" } } }, tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${window.FincontrolUtils.formatCurrency(context.raw)}` } } } } });
  }

  async function loadData() {
    try { renderLoading(); const summary = await window.FincontrolAPI.dashboardSummary(state.period); state.summary = summary; renderSummary(summary); }
    catch (error) { if (summaryCopy) summaryCopy.textContent = error.message || "Não foi possível carregar o dashboard."; if (summaryCards) summaryCards.innerHTML = `<div class="empty-state">Não foi possível carregar os dados do dashboard.</div>`; }
  }

  function renderLoading() { if (summaryCards) summaryCards.innerHTML = Array.from({ length: 4 }, () => `<article class="card summary-card skeleton-card"><span></span><span></span><span></span></article>`).join(""); }
  async function handleLogout() { try { await window.FincontrolAPI.logout(); } catch (_) { /* sessão pode já ter expirado */ } finally { window.location.href = "/login"; } }
  async function init() { try { const me = await window.FincontrolAPI.me(); state.user = me.user; await window.FincontrolLayout.renderShell(state.user, state.period, async (period) => { state.period = period; await loadData(); }, handleLogout); document.addEventListener("fincontrol:refresh", loadData); await loadData(); } catch (_) { window.location.href = "/login"; } }
  init();
});
