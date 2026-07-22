window.FincontrolUtils = (() => {
  const currencyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const dateFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
  function formatCurrency(value) { return currencyFormatter.format(Number(value || 0)); }
  function formatDate(value) { if (!value) return "-"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : dateFormatter.format(date); }
  function formatShortDate(value) { if (!value) return "-"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }); }
  function getPeriodLabel(period) { return ({ current_month: "Este mês", previous_month: "Mês passado", current_week: "Esta semana", previous_week: "Semana passada", current_year: "Este ano", today: "Hoje", yesterday: "Ontem" })[period] || period || "Período atual"; }
  function escapeHtml(text) { return String(text || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }
  return { formatCurrency, formatDate, formatShortDate, getPeriodLabel, escapeHtml };
})();
