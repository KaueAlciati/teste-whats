window.FincontrolUtils = (() => {
  const currencyFormatter = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

  const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  function formatCurrency(value) {
    const amount = Number(value || 0);
    return currencyFormatter.format(amount);
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return dateFormatter.format(date);
  }

  function formatShortDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  }

  function getPeriodLabel(period) {
    const labels = {
      current_month: "Mês atual",
      previous_month: "Mês anterior",
      current_week: "Semana atual",
      previous_week: "Semana anterior",
      current_year: "Ano atual",
      today: "Hoje",
      yesterday: "Ontem",
    };
    return labels[period] || period || "Período atual";
  }

  function escapeHtml(text) {
    return String(text || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  return {
    formatCurrency,
    formatDate,
    formatShortDate,
    getPeriodLabel,
    escapeHtml,
  };
})();
