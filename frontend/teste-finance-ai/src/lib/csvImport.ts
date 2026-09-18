/**
 * Parsing e normalização de extrato CSV para o modelo interno de
 * transação — versão de navegador da parte CSV de
 * `backend/app/core/import_parsing.py`, usada apenas no modo
 * LocalStorage (a API continua sendo o caminho principal, e a única
 * que também entende OFX por enquanto).
 *
 * Só entende "de fora para dentro": recebe o texto de um arquivo e
 * devolve linhas reconhecidas (`ParsedRow`) mais linhas que não
 * puderam ser interpretadas (`ParseIssue`). Nada aqui persiste dado
 * nenhum — isso é responsabilidade de `localStorage.ts`.
 */

export const MAX_IMPORT_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB

export class FileValidationError extends Error {}

export type ParsedRow = {
  date: string; // ISO 8601 (YYYY-MM-DD)
  description: string;
  amount: number; // sempre positivo — o sinal vira `type`
  type: "income" | "expense";
  external_id: string | null;
  line_number: number | null;
};

export type ParseIssue = {
  line_number: number | null;
  reason: string;
  raw: string;
};

// ---------------------------------------------------------------------------
// Validação de arquivo
// ---------------------------------------------------------------------------

export function validateCsvFile(filename: string, content: string): void {
  if (!filename || !filename.includes(".")) {
    throw new FileValidationError("Formato de arquivo não suportado.");
  }
  const extension = "." + filename.split(".").pop()!.toLowerCase();
  if (extension !== ".csv") {
    throw new FileValidationError("Formato de arquivo não suportado.");
  }
  if (!content) {
    throw new FileValidationError("O arquivo está vazio.");
  }
  // Aproximação de bytes (UTF-16 no navegador) — suficiente para o
  // limite de tamanho, que é uma salvaguarda, não um contrato exato.
  if (content.length * 2 > MAX_IMPORT_FILE_SIZE_BYTES) {
    throw new FileValidationError("O arquivo excede o tamanho máximo permitido.");
  }
}

// ---------------------------------------------------------------------------
// Valores monetários
// ---------------------------------------------------------------------------

const CURRENCY_NOISE = /[R$\s]/gi;

export function parseAmount(raw: string | null | undefined): number {
  if (raw === null || raw === undefined) throw new Error("valor vazio");

  let text = String(raw).replace(CURRENCY_NOISE, "").trim();
  if (!text) throw new Error("valor vazio");

  let negative = false;
  if (text.startsWith("(") && text.endsWith(")")) {
    negative = true;
    text = text.slice(1, -1);
  }
  if (text.startsWith("-")) {
    negative = true;
    text = text.slice(1);
  } else if (text.startsWith("+")) {
    text = text.slice(1);
  }

  const hasComma = text.includes(",");
  const hasDot = text.includes(".");

  if (hasComma && hasDot) {
    // O separador decimal é o que aparece por último.
    if (text.lastIndexOf(",") > text.lastIndexOf(".")) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else {
      text = text.replace(/,/g, "");
    }
  } else if (hasComma) {
    const parts = text.split(",");
    if (parts.length === 2 && parts[1].length >= 1 && parts[1].length <= 2) {
      text = text.replace(",", ".");
    } else {
      text = text.replace(/,/g, "");
    }
  }

  const value = Number(text);
  if (Number.isNaN(value)) throw new Error("valor inválido");
  return negative ? -value : value;
}

// ---------------------------------------------------------------------------
// Datas
// ---------------------------------------------------------------------------

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function isValidDate(y: number, m: number, d: number): boolean {
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}

export function parseDate(raw: string | null | undefined): string {
  const text = (raw ?? "").trim();
  if (!text) throw new Error("data vazia");

  // YYYYMMDD (ou com hora colada) — igual ao DTPOSTED do OFX.
  const digitsOnly = text.match(/^(\d{8})/);
  if (digitsOnly) {
    const y = parseInt(digitsOnly[1].slice(0, 4), 10);
    const m = parseInt(digitsOnly[1].slice(4, 6), 10);
    const d = parseInt(digitsOnly[1].slice(6, 8), 10);
    if (isValidDate(y, m, d)) return `${y}-${pad2(m)}-${pad2(d)}`;
  }

  const patterns: Array<[RegExp, (m: RegExpMatchArray) => string | null]> = [
    [/^(\d{4})-(\d{2})-(\d{2})$/, (m) => (isValidDate(+m[1], +m[2], +m[3]) ? `${m[1]}-${m[2]}-${m[3]}` : null)],
    [/^(\d{2})\/(\d{2})\/(\d{4})$/, (m) => (isValidDate(+m[3], +m[2], +m[1]) ? `${m[3]}-${m[2]}-${m[1]}` : null)],
    [/^(\d{2})-(\d{2})-(\d{4})$/, (m) => (isValidDate(+m[3], +m[2], +m[1]) ? `${m[3]}-${m[2]}-${m[1]}` : null)],
    [/^(\d{4})\/(\d{2})\/(\d{2})$/, (m) => (isValidDate(+m[1], +m[2], +m[3]) ? `${m[1]}-${m[2]}-${m[3]}` : null)],
    [/^(\d{2})\.(\d{2})\.(\d{4})$/, (m) => (isValidDate(+m[3], +m[2], +m[1]) ? `${m[3]}-${m[2]}-${m[1]}` : null)],
    [
      /^(\d{2})\/(\d{2})\/(\d{2})$/,
      (m) => {
        const year = 2000 + +m[3];
        return isValidDate(year, +m[2], +m[1]) ? `${year}-${m[2]}-${m[1]}` : null;
      },
    ],
  ];

  for (const [pattern, toIso] of patterns) {
    const match = text.match(pattern);
    if (match) {
      const iso = toIso(match);
      if (iso) return iso;
    }
  }

  throw new Error(`formato de data não reconhecido: ${text}`);
}

// ---------------------------------------------------------------------------
// CSV
// ---------------------------------------------------------------------------

const HEADER_ALIASES: Record<string, string[]> = {
  date: ["data", "data lancamento", "data lançamento", "date", "data mov", "data movimento"],
  description: [
    "descricao", "descrição", "historico", "histórico", "description",
    "lancamento", "lançamento", "detalhes",
  ],
  amount: ["valor", "amount", "valor (r$)", "montante"],
  debit: ["debito", "débito", "debit", "saida", "saída"],
  credit: ["credito", "crédito", "credit", "entrada"],
  id: ["id", "documento", "identificador", "num doc", "nº doc"],
};

function stripAccentsLower(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function matchHeader(headerCells: string[]): Record<string, number> {
  const normalizedCells = headerCells.map(stripAccentsLower);
  const mapping: Record<string, number> = {};
  for (const [role, aliases] of Object.entries(HEADER_ALIASES)) {
    const normalizedAliases = aliases.map(stripAccentsLower);
    for (let idx = 0; idx < normalizedCells.length; idx++) {
      if (normalizedAliases.includes(normalizedCells[idx])) {
        mapping[role] = idx;
        break;
      }
    }
  }
  return mapping;
}

function sniffDelimiter(sample: string): string {
  const semicolons = (sample.match(/;/g) ?? []).length;
  const firstLine = sample.split("\n", 1)[0] ?? "";
  const commasInHeader = (firstLine.match(/,/g) ?? []).length;
  if (semicolons > 0 && semicolons >= commasInHeader) return ";";
  return ",";
}

/** Parser de linha CSV simples, com suporte a aspas (RFC 4180). */
function parseCsvLines(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char === "\r") {
      // ignora — tratado junto com \n
    } else {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

export function parseCsv(text: string): { parsed: ParsedRow[]; issues: ParseIssue[] } {
  // BOM UTF-8, se presente.
  const cleanText = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;

  const delimiter = sniffDelimiter(cleanText);
  const rawRows = parseCsvLines(cleanText, delimiter).filter((row) =>
    row.some((cell) => cell.trim() !== ""),
  );

  if (rawRows.length === 0) {
    return { parsed: [], issues: [{ line_number: null, reason: "Arquivo não contém movimentações.", raw: "" }] };
  }

  const headerMapping = matchHeader(rawRows[0]);
  const dataRows = rawRows.slice(1);

  const hasHeader = headerMapping.date !== undefined || headerMapping.amount !== undefined;
  if (!hasHeader) {
    return {
      parsed: [],
      issues: [{
        line_number: 1,
        reason: "Não foi possível identificar as colunas de data e valor no arquivo.",
        raw: "",
      }],
    };
  }

  const hasSingleAmount = headerMapping.amount !== undefined;
  const hasSplitAmount = headerMapping.debit !== undefined || headerMapping.credit !== undefined;

  if (!hasSingleAmount && !hasSplitAmount) {
    return {
      parsed: [],
      issues: [{ line_number: 1, reason: "Não foi possível identificar a coluna de valor no arquivo.", raw: "" }],
    };
  }
  if (headerMapping.date === undefined) {
    return {
      parsed: [],
      issues: [{ line_number: 1, reason: "Não foi possível identificar a coluna de data no arquivo.", raw: "" }],
    };
  }

  const parsed: ParsedRow[] = [];
  const issues: ParseIssue[] = [];

  dataRows.forEach((row, index) => {
    const lineNumber = index + 2; // linha 1 é o cabeçalho
    const rawLine = row.join(delimiter);

    const cell = (role: string): string => {
      const idx = headerMapping[role];
      if (idx === undefined || idx >= row.length) return "";
      return (row[idx] ?? "").trim();
    };

    const dateRaw = cell("date");
    const description = cell("description") || "(sem descrição)";
    const externalId = cell("id") || null;

    let isoDate: string;
    try {
      isoDate = parseDate(dateRaw);
    } catch {
      issues.push({ line_number: lineNumber, reason: "Data inválida", raw: rawLine });
      return;
    }

    let amountValue: number;
    try {
      if (hasSingleAmount) {
        amountValue = parseAmount(cell("amount"));
      } else {
        const debitRaw = cell("debit");
        const creditRaw = cell("credit");
        if (creditRaw) {
          amountValue = Math.abs(parseAmount(creditRaw));
        } else if (debitRaw) {
          amountValue = -Math.abs(parseAmount(debitRaw));
        } else {
          issues.push({ line_number: lineNumber, reason: "Valor não identificado", raw: rawLine });
          return;
        }
      }
    } catch {
      issues.push({ line_number: lineNumber, reason: "Valor não identificado", raw: rawLine });
      return;
    }

    if (amountValue === 0) {
      issues.push({ line_number: lineNumber, reason: "Movimentação com valor zero", raw: rawLine });
      return;
    }

    parsed.push({
      date: isoDate,
      description,
      amount: Math.abs(amountValue),
      type: amountValue > 0 ? "income" : "expense",
      external_id: externalId,
      line_number: lineNumber,
    });
  });

  return { parsed, issues };
}
