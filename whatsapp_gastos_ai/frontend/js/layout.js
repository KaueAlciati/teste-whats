window.FincontrolLayout = (() => {
  const icon = (name) => `<i data-lucide="${name}" aria-hidden="true"></i>`;

  function initials(user) {
    return String(user?.name || "FC").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  }

  function buildSidebar(user, activePage = "dashboard") {
    const links = [
      ["dashboard", "/dashboard", "layout-dashboard", "Dashboard"],
      ["transactions", "#recent-transactions", "arrow-left-right", "Movimentações"],
      ["expenses", "#summary-cards", "trending-down", "Gastos"],
      ["income", "#summary-cards", "trending-up", "Receitas"],
      ["invoices", "#summary-cards", "file-text", "Faturas"],
      ["goals", "#goals-list", "target", "Metas"],
      ["charts", "#cash-flow-chart", "bar-chart-3", "Gráficos"],
      ["reports", "#ai-summary", "file-bar-chart", "Relatórios"],
      ["reminders", "#reminders-list", "bell", "Lembretes"],
      ["conversations", "#ai-summary", "message-circle", "Conversas da IA"],
    ];
    const renderLink = ([key, href, lucide, label]) => `<a class="sidebar-link ${activePage === key ? "is-active" : ""}" href="${href}">${icon(lucide)}<span>${label}</span></a>`;
    return `
      <div class="sidebar-brand">
        <div class="brand-lockup"><div class="brand-mark">FC</div><div><strong>Fincontrol</strong><small>IA Financeira</small></div></div>
      </div>
      <nav class="sidebar-nav" aria-label="Menu principal">
        ${links.slice(0, 1).map(renderLink).join("")}
        <div class="sidebar-section-label">Finanças</div>
        ${links.slice(1, 7).map(renderLink).join("")}
        <div class="sidebar-section-label">Atendimento</div>
        ${links.slice(7).map(renderLink).join("")}
      </nav>
      <div class="sidebar-footer">
        <a class="sidebar-link ${activePage === "settings" ? "is-active" : ""}" href="/configuracoes">${icon("settings")}<span>Configurações</span></a>
        <button id="sidebar-logout" class="btn btn-ghost" type="button">${icon("log-out")}<span>Sair</span></button>
        <div class="sidebar-user"><span class="avatar">${initials(user)}</span><div><strong>${window.FincontrolUtils.escapeHtml(user?.name || "Usuário")}</strong><small>${window.FincontrolUtils.escapeHtml(user?.email || user?.phone || "Conta Fincontrol")}</small></div></div>
      </div>
    `;
  }

  function buildTopbar(user, period) {
    return `
      <div class="topbar-inner">
        <button id="sidebar-toggle" class="mobile-menu-button" type="button" aria-label="Abrir menu" aria-expanded="false">${icon("menu")}</button>
        <div class="topbar-context"><span class="topbar-label">Fincontrol</span><strong>Visão geral das suas finanças</strong></div>
        <div class="topbar-actions">
          <label class="period-select"><span class="topbar-period-label">Período</span><select id="period-select" aria-label="Selecionar período">
            <option value="current_month" ${period === "current_month" ? "selected" : ""}>Este mês</option>
            <option value="previous_month" ${period === "previous_month" ? "selected" : ""}>Mês passado</option>
            <option value="current_week" ${period === "current_week" ? "selected" : ""}>Esta semana</option>
            <option value="previous_week" ${period === "previous_week" ? "selected" : ""}>Semana passada</option>
            <option value="current_year" ${period === "current_year" ? "selected" : ""}>Este ano</option>
            <option value="today" ${period === "today" ? "selected" : ""}>Hoje</option>
          </select></label>
          <button id="refresh-dashboard" class="icon-button" type="button" aria-label="Atualizar dados">${icon("refresh-cw")}</button>
          <span class="topbar-avatar avatar" aria-label="Usuário">${initials(user)}</span>
        </div>
      </div>
    `;
  }

  async function renderShell(user, period, onPeriodChange, onLogout) {
    const sidebar = document.getElementById("sidebar");
    const topbar = document.getElementById("topbar");
    if (sidebar) sidebar.innerHTML = buildSidebar(user, window.location.pathname.includes("configuracoes") ? "settings" : "dashboard");
    if (topbar) topbar.innerHTML = buildTopbar(user, period);

    const toggle = document.getElementById("sidebar-toggle");
    const backdrop = document.getElementById("sidebar-backdrop");
    const closeMenu = () => { document.body.classList.remove("sidebar-open"); if (backdrop) backdrop.hidden = true; if (toggle) toggle.setAttribute("aria-expanded", "false"); };
    toggle?.addEventListener("click", () => { const open = !document.body.classList.contains("sidebar-open"); document.body.classList.toggle("sidebar-open", open); if (backdrop) backdrop.hidden = !open; toggle.setAttribute("aria-expanded", String(open)); });
    backdrop?.addEventListener("click", closeMenu);
    sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));

    document.getElementById("period-select")?.addEventListener("change", (event) => onPeriodChange?.(event.target.value));
    document.getElementById("sidebar-logout")?.addEventListener("click", onLogout);
    document.getElementById("refresh-dashboard")?.addEventListener("click", () => document.dispatchEvent(new CustomEvent("fincontrol:refresh")));
    window.lucide?.createIcons?.();
  }

  return { renderShell };
})();
