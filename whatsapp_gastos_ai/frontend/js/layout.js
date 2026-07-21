window.FincontrolLayout = (() => {
  function buildSidebar(user) {
    return `
      <div class="sidebar-brand">
        <div class="brand-mark" style="margin-bottom:18px;">FC</div>
        <p class="eyebrow">Fincontrol</p>
        <h2 style="margin:0 0 8px;">${window.FincontrolUtils.escapeHtml(user?.name || "Painel")}</h2>
        <p style="margin:0;color:rgba(237,248,238,.78);line-height:1.5;">
          Acompanhamento financeiro integrado ao agente multicanal.
        </p>
      </div>

      <nav class="sidebar-nav" style="margin-top:28px;display:grid;gap:10px;">
        <a class="pill" href="#summary-cards">Visão geral</a>
        <a class="pill" href="#recent-transactions">Movimentações</a>
        <a class="pill" href="#reminders-list">Lembretes</a>
        <a class="pill" href="#ai-summary">Resumo IA</a>
      </nav>

      <div style="margin-top:auto;display:grid;gap:14px;">
        <div class="list-item" style="background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.1);color:#edf8ee;">
          <strong>${window.FincontrolUtils.escapeHtml(user?.email || user?.phone || "Usuário")}</strong>
          <small>${window.FincontrolUtils.escapeHtml(user?.role || "user")}</small>
        </div>
        <button id="sidebar-logout" class="btn btn-ghost" type="button">Sair</button>
      </div>
    `;
  }

  function buildTopbar(user, period) {
    return `
      <div class="topbar-inner" style="max-width:var(--container);margin:0 auto;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:20px;">
        <div>
          <p class="eyebrow" style="color:var(--muted);margin-bottom:6px;">Dashboard web</p>
          <strong style="font-size:1.08rem;">${window.FincontrolUtils.escapeHtml(user?.name || "Usuário")}</strong>
        </div>
        <div class="meta-row">
          <label class="period-select">
            <span>Período</span>
            <select id="period-select">
              <option value="current_month" ${period === "current_month" ? "selected" : ""}>Mês atual</option>
              <option value="previous_month" ${period === "previous_month" ? "selected" : ""}>Mês anterior</option>
              <option value="current_week" ${period === "current_week" ? "selected" : ""}>Semana atual</option>
              <option value="previous_week" ${period === "previous_week" ? "selected" : ""}>Semana anterior</option>
              <option value="current_year" ${period === "current_year" ? "selected" : ""}>Ano atual</option>
              <option value="today" ${period === "today" ? "selected" : ""}>Hoje</option>
            </select>
          </label>
        </div>
      </div>
    `;
  }

  async function renderShell(user, period, onPeriodChange, onLogout) {
    const sidebar = document.getElementById("sidebar");
    const topbar = document.getElementById("topbar");
    if (sidebar) sidebar.innerHTML = buildSidebar(user);
    if (topbar) topbar.innerHTML = buildTopbar(user, period);

    const periodSelect = document.getElementById("period-select");
    if (periodSelect && typeof onPeriodChange === "function") {
      periodSelect.addEventListener("change", (event) => onPeriodChange(event.target.value));
    }

    const logoutButton = document.getElementById("sidebar-logout");
    if (logoutButton && typeof onLogout === "function") {
      logoutButton.addEventListener("click", onLogout);
    }

    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  return {
    renderShell,
  };
})();
