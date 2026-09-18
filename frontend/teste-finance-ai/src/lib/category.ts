/**
 * Normalização de categoria de transação (frontend).
 *
 * Espelha `backend/app/core/categorization.py` — mesma regra de
 * negócio nas duas camadas, cada uma na sua linguagem, para o modo
 * API e o modo LocalStorage produzirem os mesmos agrupamentos.
 *
 * Categoria é texto livre digitado pelo usuário: "Alimentação",
 * "alimentação" e "ALIMENTAÇÃO" precisam ser tratadas como a mesma
 * categoria nos filtros e nos Insights, sem exigir nenhuma migração
 * dos dados já salvos.
 */

/** Capitalização amigável por palavra, para exibição/gravação. */
export function formatCategoryLabel(raw: string): string {
  const text = (raw ?? "").trim().replace(/\s+/g, " ");
  if (!text) return text;
  return text
    .split(" ")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1).toLowerCase() : word))
    .join(" ");
}

/** Chave de agrupamento estável: minúscula, sem acento, sem espaço duplicado. */
export function normalizeCategoryKey(raw: string): string {
  const text = (raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  return text || "sem categoria";
}

/**
 * Motor de sugestão de categoria por regra/palavra-chave — espelha
 * `backend/app/core/categorization.py` (`CATEGORY_RULES`). Usado na
 * importação de extrato no modo local, para o mesmo comportamento
 * de auto-categorização existir nos dois modos. Se alterar as regras
 * de um lado, replicar do outro.
 */
const CATEGORY_RULES: Array<[string, string[]]> = [
  ["Receita", ["salario", "salário", "pagamento salario", "pro labore", "pró labore"]],
  ["Alimentação", ["ifood", "rappi", "restaurante", "lanchonete", "padaria", "supermercado", "mercado"]],
  ["Transporte", ["uber", "99", "taxi", "táxi", "metro", "metrô", "onibus", "ônibus"]],
  ["Assinaturas", ["netflix", "spotify", "prime video", "disney", "hbo", "youtube premium"]],
  ["Saúde", ["farmacia", "farmácia", "drogaria", "hospital", "clinica", "clínica"]],
  ["Combustível", ["posto", "combustivel", "combustível", "gasolina", "etanol"]],
  ["Moradia", ["aluguel", "condominio", "condomínio", "energia", "luz", "iptu"]],
  ["Lazer", ["cinema", "teatro", "ingresso", "show"]],
];

export function suggestCategory(description: string, normalizedDescription: string): string | null {
  const haystack = normalizedDescription || (description ?? "").toLowerCase();
  for (const [category, keywords] of CATEGORY_RULES) {
    for (const keyword of keywords) {
      if (haystack.includes(keyword)) return category;
    }
  }
  return null;
}
