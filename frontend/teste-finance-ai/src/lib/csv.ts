import type { Transaction } from "@/lib/api";

/**
 * Exportação de transações para CSV — recurso sugerido em
 * docs/IDEIAS.md ("rápidas de fazer, impacto imediato"): útil pra
 * declaração de imposto de renda ou conferência manual, e é só
 * formatar a mesma lista que já existe em /transactions.
 *
 * Roda inteiramente no navegador (sem chamada ao backend), então
 * funciona igual nos dois modos do app — API e localStorage — já que
 * opera sobre a lista de transações que a tela já carregou.
 *
 * Formato pensado para abrir bem no Excel/LibreOffice em pt-BR:
 * delimitador ";" (porque "," já é o separador decimal daqui) e um
 * BOM UTF-8 no início do arquivo, sem o qual acentos aparecem
 * corrompidos quando o Excel abre o CSV por duplo-clique.
 */

function escapeCsvField(value: string): string {
  // Preciso de aspas quando o campo contém o delimitador, aspas ou
  // quebra de linha — regra padrão do formato CSV (RFC 4180).
  if (/[";\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function formatAmountForSpreadsheet(amount: number): string {
  // "," como separador decimal, sem separador de milhar — é o que o
  // Excel em pt-BR espera pra reconhecer a célula como número, em vez
  // de importar tudo como texto.
  return amount.toFixed(2).replace(".", ",");
}

export function buildTransactionsCsv(transactions: Transaction[]): string {
  const header = ["Data", "Descrição", "Categoria", "Tipo", "Valor (R$)"];
  const rows = transactions.map((t) => [
    new Date(t.date).toLocaleDateString("pt-BR"),
    t.description,
    t.category,
    t.type === "income" ? "Entrada" : "Saída",
    formatAmountForSpreadsheet(t.amount),
  ]);

  const lines = [header, ...rows].map((row) =>
    row.map(escapeCsvField).join(";"),
  );

  const BOM = "\uFEFF";
  return BOM + lines.join("\r\n");
}

export function downloadTransactionsCsv(transactions: Transaction[]): void {
  const csv = buildTransactionsCsv(transactions);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const today = new Date().toISOString().slice(0, 10);
  const link = document.createElement("a");
  link.href = url;
  link.download = `extrato-financeai-${today}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
