(function () {
  "use strict";

  const apiBase = "/api";
  const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  async function request(path, options) {
    const response = await fetch(`${apiBase}${path}`, { credentials: "include", headers: { "Content-Type": "application/json" }, ...(options || {}) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) throw new Error(payload.message || `Erro HTTP ${response.status}`);
    return payload.data ?? payload;
  }

  function formatMoney(value) { return money.format(Number(value || 0)); }
  function setText(element, value) { if (element) element.textContent = value; }

  async function loadDashboard() {
    const container = document.querySelector("#content > .container-fluid");
    if (!container) return;
    try {
      const me = await request("/auth/me");
      const user = me.user || me;
      document.querySelectorAll(".img-profile, .sidebar-user-name").forEach((node) => { if (node.tagName === "IMG") node.alt = user.name || "Usuário"; else node.textContent = user.name || "Usuário"; });
      const rows = Array.from(container.children).filter((node) => node.classList.contains("row"));
      const cards = rows[0];
      const summary = await request("/dashboard/summary?period=current_month");
      const values = [summary.cards?.balance?.value, summary.cards?.income?.value, summary.cards?.expense?.value, summary.cards?.pending_invoice?.value];
      cards?.querySelectorAll(".card .h5 span").forEach((node, index) => setText(node, formatMoney(values[index])));
      const title = container.querySelector("h3, h1");
      if (title) setText(title, "Dashboard");
      const summaryText = summary.ai_summary?.text || "Resumo financeiro do período atual.";
      const paragraph = container.querySelector(".reference-summary-text");
      if (paragraph) setText(paragraph, summaryText);
      updateCharts(container, summary.charts || {});
      renderRecentData(container, summary);
    } catch (error) {
      if (error.message.includes("401") || error.message.toLowerCase().includes("autentic")) window.location.href = "/login";
      else console.error("Falha ao carregar dados financeiros:", error);
    }
  }

  function updateCharts(container, charts) {
    const canvases = container.querySelectorAll("canvas[data-bss-chart]");
    const flow = charts.cash_flow || { labels: [], income: [], expense: [] };
    const categories = charts.categories || [];
    const chartValues = [
      { labels: flow.labels || [], datasets: [{ label: "Entradas", data: flow.income || [], borderColor: "#15803D", backgroundColor: "rgba(21,128,61,.12)", fill: true }, { label: "Saídas", data: flow.expense || [], borderColor: "#DC2626", backgroundColor: "rgba(220,38,38,.08)", fill: true }] },
      { labels: categories.map((item) => item.label), datasets: [{ data: categories.map((item) => item.value), backgroundColor: categories.map((item) => item.color || "#15803D"), borderColor: "#fff", borderWidth: 2 }] },
    ];
    canvases.forEach((canvas, index) => { const chart = canvas.chart; const data = chartValues[index]; if (!chart || !data) return; chart.data.labels = data.labels; chart.data.datasets = data.datasets; chart.update(); });
  }

  function renderRecentData(container, summary) {
    const target = container.querySelector(".reference-recent-data");
    if (!target) return;
    const items = summary.recent_transactions || [];
    target.innerHTML = items.length ? items.slice(0, 5).map((item) => `<div class="d-flex justify-content-between border-bottom py-2"><span>${escapeHtml(item.description || "Movimentação")}</span><strong>${formatMoney(item.amount)}</strong></div>`).join("") : "<p class=\"text-muted mb-0\">Nenhuma movimentação encontrada neste período.</p>";
  }

  function escapeHtml(value) { return String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }

  function bindLogin() {
    const form = document.getElementById("login-form") || document.querySelector("form.user");
    if (!form) return;
    const identifier = form.querySelector("#identifier, [name=email]"); const password = form.querySelector("#password, [name=password]"); const feedback = document.getElementById("login-feedback");
    form.addEventListener("submit", async (event) => { event.preventDefault(); try { await request("/auth/login", { method: "POST", body: JSON.stringify({ identifier: identifier.value.trim(), password: password.value, remember_me: Boolean(form.querySelector("#remember_me, input[type=checkbox]")?.checked) }) }); window.location.href = "/dashboard"; } catch (error) { if (feedback) feedback.textContent = error.message || "E-mail, telefone ou senha inválidos."; else alert(error.message); } });
  }

  function bindRegister() {
    const form = document.getElementById("register-form") || document.querySelector("form.user");
    if (!form || window.location.pathname !== "/register") return;
    const email = form.querySelector("#email, [name=email]"); const password = form.querySelector("#password, [name=password]"); const repeat = form.querySelector("#confirm_password, [name=password_repeat]"); const first = form.querySelector("#name, [name=first_name]"); const last = form.querySelector("[name=last_name]");
    let phone = form.querySelector("#phone");
    if (!phone) { const wrapper = document.createElement("div"); wrapper.className = "mb-3"; wrapper.innerHTML = '<input class="form-control form-control-user" type="tel" id="phone" placeholder="Telefone" required>'; (email.closest(".mb-3") || email.parentElement).after(wrapper); phone = wrapper.querySelector("#phone"); }
    form.addEventListener("submit", async (event) => { event.preventDefault(); if (password.value !== repeat.value) { alert("As senhas não conferem."); return; } try { await request("/auth/register", { method: "POST", body: JSON.stringify({ name: `${first.value} ${last?.value || ""}`.trim(), email: email.value.trim(), phone: phone.value.trim(), password: password.value, confirm_password: repeat.value, accept_terms: true }) }); window.location.href = "/login"; } catch (error) { alert(error.message || "Não foi possível criar a conta."); } });
  }

  document.addEventListener("DOMContentLoaded", () => { bindLogin(); bindRegister(); if (window.location.pathname === "/dashboard" || document.body.id === "page-top") loadDashboard(); });
})();
