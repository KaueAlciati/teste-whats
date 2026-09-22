"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowUpCircle, ArrowDownCircle, Search, Trash2, Pencil, Download, UploadCloud, SlidersHorizontal, X, ChevronDown, FileSearch } from "lucide-react";
import { storage } from "@/lib/storage";
import { api, HttpError, type Transaction } from "@/lib/api";
import { AppLayout } from "@/components/AppLayout";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { useToast } from "@/contexts/ToastContext";
import { formatCurrency } from "@/lib/utils";
import { formatCategoryLabel, normalizeCategoryKey } from "@/lib/category";
import { StatementImportDialog } from "@/components/StatementImportDialog";

type SourceFilter = "all" | "manual" | "import";
type ExportFormat = "xlsx" | "csv";

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [filteredTransactions, setFilteredTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [viewingAttachmentId, setViewingAttachmentId] = useState<number | null>(null);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const handleFetchError = useHandleFetchError();
  const { addToast } = useToast();

  const fetchTransactions = useCallback(async () => {
    try {
      const data = await storage.getTransactions();
      setTransactions(data);
      setFilteredTransactions(data);
    } catch (error) {
      await handleFetchError(error, "Erro ao carregar transações:");
    } finally {
      setLoading(false);
    }
  }, [handleFetchError]);

  useEffect(() => {
    fetchTransactions();

    // O botão flutuante "+" (NewTransactionModal) existe em todas as
    // páginas e dispara esse evento ao criar uma transação. Sem este
    // listener, quem estivesse na tela de Extrato só via a nova
    // transação depois de recarregar a página manualmente.
    window.addEventListener("transactions-changed", fetchTransactions);
    return () => window.removeEventListener("transactions-changed", fetchTransactions);
  }, [fetchTransactions]);

  // Lista de categorias que realmente existem no histórico, em vez de
  // uma lista fixa — assim o filtro sempre reflete o que o usuário
  // cadastrou. Categoria é texto livre, então duas grafias da mesma
  // categoria ("Alimentação" / "alimentação") são agrupadas numa única
  // opção de filtro, usando a chave normalizada (ver src/lib/category.ts).
  const availableCategories = useMemo(() => {
    const byKey = new Map<string, string>();
    for (const t of transactions) {
      const key = normalizeCategoryKey(t.category);
      if (!byKey.has(key)) byKey.set(key, formatCategoryLabel(t.category));
    }
    return Array.from(byKey.entries())
      .map(([key, label]) => ({ key, label }))
      .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
  }, [transactions]);

  const hasActiveFilters =
    sourceFilter !== "all" || categoryFilter !== "all" || dateFrom !== "" || dateTo !== "";

  function clearFilters() {
    setSourceFilter("all");
    setCategoryFilter("all");
    setDateFrom("");
    setDateTo("");
  }

  useEffect(() => {
    // Datas de transação são strings ISO (YYYY-MM-DD ou com horário);
    // comparar os 10 primeiros caracteres evita problema de fuso do
    // `new Date(...)` e casa exatamente com o formato de <input type="date">.
    const filtered = transactions
      .filter((t) =>
        t.description.toLowerCase().includes(search.toLowerCase()) ||
        t.category.toLowerCase().includes(search.toLowerCase())
      )
      .filter((t) => {
        if (sourceFilter === "all") return true;
        const source = transactionSourceFilter(t.source);
        return source === sourceFilter;
      })
      .filter((t) => categoryFilter === "all" || normalizeCategoryKey(t.category) === categoryFilter)
      .filter((t) => !dateFrom || t.date.slice(0, 10) >= dateFrom)
      .filter((t) => !dateTo || t.date.slice(0, 10) <= dateTo);
    setFilteredTransactions(filtered);
  }, [search, sourceFilter, categoryFilter, dateFrom, dateTo, transactions]);

  async function handleExport(format: ExportFormat) {
    if ((dateFrom && !dateTo) || (!dateFrom && dateTo)) {
      addToast("error", "Informe as duas datas para exportar um intervalo.");
      return;
    }
    setExportMenuOpen(false);
    setExportingFormat(format);
    try {
      const exported = await api.exportTransactions({
        format,
        startDate: dateFrom || undefined,
        endDate: dateTo || undefined,
      });
      downloadBlob(exported.blob, exported.filename);
      addToast(
        "success",
        format === "xlsx" ? "Extrato exportado em Excel." : "Extrato exportado em CSV.",
      );
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) {
        addToast("error", "Não há transações no período para exportar.");
      } else {
        await handleFetchError(error, "Erro ao exportar extrato:");
      }
    } finally {
      setExportingFormat(null);
    }
  }

  async function handleDelete(transaction: Transaction) {
    if (!transaction.id) return;

    // Mostrar o valor formatado, e não só a descrição, reduz o risco
    // de excluir a transação errada quando duas têm nomes parecidos —
    // ver docs/IDEIAS.md.
    const signal = transaction.type === "expense" ? "-" : "+";
    const confirmed = window.confirm(
      `Excluir a transação "${transaction.description}" (${signal} ${formatCurrency(transaction.amount)})?\n\nEssa ação não pode ser desfeita.`
    );
    if (!confirmed) return;

    setDeletingId(transaction.id);
    try {
      await storage.deleteTransaction(transaction.id);
      window.dispatchEvent(new Event("transactions-changed"));
    } catch (err) {
      await handleFetchError(err, "Erro ao excluir transação:");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleViewAttachment(transaction: Transaction) {
    if (!transaction.id) return;
    const viewer = window.open("", "_blank");
    if (viewer) viewer.opener = null;
    setViewingAttachmentId(transaction.id);
    try {
      const blob = await api.getTransactionAttachment(transaction.id);
      const url = URL.createObjectURL(blob);
      if (viewer) {
        viewer.location.href = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      viewer?.close();
      await handleFetchError(error, "Erro ao abrir comprovante:");
    } finally {
      setViewingAttachmentId(null);
    }
  }

  return (
    <AppLayout>
      <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4">
        <div>
          <h1 className="text-3xl font-bold">Extrato</h1>
          <p className="text-zinc-400">Gerencie seu histórico financeiro</p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative group flex-1 sm:w-64">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors"
              size={18}
            />
            <input
              type="text"
              placeholder="Buscar transações..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 transition-all w-full"
            />
          </div>

          <div className="relative shrink-0">
            <button
              onClick={() => setExportMenuOpen((open) => !open)}
              disabled={exportingFormat !== null}
              aria-label="Exportar extrato"
              aria-haspopup="menu"
              aria-expanded={exportMenuOpen}
              className="flex h-[42px] items-center justify-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3 text-sm font-medium text-emerald-400 transition-all hover:bg-emerald-500/15 active:scale-95 disabled:opacity-50 sm:px-4"
            >
              <Download size={18} />
              <span>{exportingFormat ? "Exportando..." : "Exportar"}</span>
              <ChevronDown size={15} />
            </button>
            {exportMenuOpen && exportingFormat === null && (
              <div role="menu" className="absolute right-0 top-full z-30 mt-2 w-44 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 p-1 shadow-xl">
                <button role="menuitem" onClick={() => void handleExport("xlsx")} className="w-full rounded-lg px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900 hover:text-emerald-400">Excel (.xlsx)</button>
                <button role="menuitem" onClick={() => void handleExport("csv")} className="w-full rounded-lg px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900 hover:text-emerald-400">CSV (.csv)</button>
              </div>
            )}
          </div>

          <button
            onClick={() => setImportOpen(true)}
            aria-label="Importar extrato bancário"
            title="Importar extrato bancário"
            className="shrink-0 flex items-center justify-center gap-2 h-[42px] w-[42px] sm:w-auto sm:px-4 rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-emerald-500/40 hover:text-emerald-400 active:scale-95 transition-all text-sm font-medium"
          >
            <UploadCloud size={18} />
            <span className="hidden sm:inline">Importar extrato</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            { key: "all", label: "Todas" },
            { key: "manual", label: "Manuais" },
            { key: "import", label: "Importadas" },
          ] as { key: SourceFilter; label: string }[]
        ).map((option) => (
          <button
            key={option.key}
            onClick={() => setSourceFilter(option.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              sourceFilter === option.key
                ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400"
                : "border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
            }`}
          >
            {option.label}
          </button>
        ))}

        <div className="w-px h-5 bg-zinc-800 mx-1" />

        <button
          onClick={() => setFiltersOpen((open) => !open)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            filtersOpen || hasActiveFilters
              ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400"
              : "border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
          }`}
          aria-expanded={filtersOpen}
        >
          <SlidersHorizontal size={13} />
          Categoria e período
          {hasActiveFilters && (categoryFilter !== "all" || dateFrom || dateTo) && (
            <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
          )}
        </button>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X size={13} />
            Limpar filtros
          </button>
        )}
      </div>

      {filtersOpen && (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="text-xs text-zinc-500 space-y-1">
            Categoria
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="block w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20"
            >
              <option value="all">Todas as categorias</option>
              {availableCategories.map((category) => (
                <option key={category.key} value={category.key}>
                  {category.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-zinc-500 space-y-1">
            De
            <input
              type="date"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)}
              className="block w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 [color-scheme:dark]"
            />
          </label>

          <label className="text-xs text-zinc-500 space-y-1">
            Até
            <input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)}
              className="block w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 [color-scheme:dark]"
            />
          </label>
        </div>
      )}

      {loading ? (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8 text-center text-zinc-500">
          Carregando...
        </div>
      ) : filteredTransactions.length === 0 ? (
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8 text-center text-zinc-500">
          {transactions.length === 0
            ? "Nenhuma transação ainda. Toque no botão + para adicionar a primeira."
            : "Nenhuma transação encontrada para essa busca/filtros."}
        </div>
      ) : (
        <>
          {/* Lista em cartões — abaixo de "sm". Uma tabela apertada em
              tela de celular vira scroll horizontal, que é fácil de não
              perceber que existe; uma lista empilhada lê melhor com o
              polegar e evita esse problema por completo. */}
          <div className="sm:hidden space-y-3">
            {filteredTransactions.map((t) => (
              <div
                key={t.id}
                className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    {t.type === "income" ? (
                      <ArrowUpCircle className="text-emerald-500 shrink-0" size={20} />
                    ) : (
                      <ArrowDownCircle className="text-rose-500 shrink-0" size={20} />
                    )}
                    <div className="min-w-0">
                      <p className="font-medium truncate">{t.description}</p>
                      <span className="inline-block mt-1 bg-zinc-800 px-2 py-0.5 rounded-md text-xs text-zinc-400">
                        {t.category}
                      </span>
                      <TransactionSourceBadge source={t.source} mobile />
                      {t.has_attachment && (
                        <button
                          onClick={() => void handleViewAttachment(t)}
                          disabled={viewingAttachmentId === t.id}
                          className="mt-2 flex items-center gap-1.5 text-xs font-medium text-sky-400 hover:text-sky-300 disabled:opacity-50"
                        >
                          <FileSearch size={13} />
                          {viewingAttachmentId === t.id ? "Abrindo..." : "Mostrar comprovante"}
                        </button>
                      )}
                    </div>
                  </div>
                  <p
                    className={`font-figures font-bold whitespace-nowrap shrink-0 ${t.type === "income" ? "text-emerald-500" : "text-zinc-100"}`}
                  >
                    {t.type === "expense" ? "- " : "+ "}
                    {new Intl.NumberFormat("pt-BR", {
                      style: "currency",
                      currency: "BRL",
                    }).format(t.amount)}
                  </p>
                </div>

                <div className="flex items-center justify-between mt-3 pt-3 border-t border-zinc-800/70">
                  <p className="text-zinc-500 text-xs">
                    {formatTransactionDate(t.date)}
                  </p>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => window.dispatchEvent(new CustomEvent("open-transaction-modal", { detail: t }))}
                      aria-label={`Editar transação ${t.description}`}
                      className="flex h-11 w-11 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-emerald-500 transition-colors"
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      onClick={() => handleDelete(t)}
                      disabled={deletingId === t.id}
                      aria-label={`Excluir transação ${t.description}`}
                      className="flex h-11 w-11 items-center justify-center rounded-lg text-zinc-500 hover:bg-rose-500/10 hover:text-rose-500 transition-colors disabled:opacity-50"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Tabela — a partir de "sm". Continua com scroll horizontal
              próprio (não na página inteira) para telas médias apertadas. */}
          <div className="hidden sm:block bg-zinc-900/50 border border-zinc-800 rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-950/50 text-zinc-500 text-xs uppercase font-bold">
                    <th className="p-4">Descrição</th>
                    <th className="p-4">Valor</th>
                    <th className="p-4">Categoria</th>
                    <th className="p-4 text-right">Data</th>
                    <th className="p-4 text-right">
                      <span className="sr-only">Ações</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {filteredTransactions.map((t) => (
                    <tr
                      key={t.id}
                      className="group hover:bg-zinc-800/30 transition-colors"
                    >
                      <td className="p-4 flex items-center gap-3">
                        {t.type === "income" ? (
                          <ArrowUpCircle className="text-emerald-500 shrink-0" size={18} />
                        ) : (
                          <ArrowDownCircle className="text-rose-500 shrink-0" size={18} />
                        )}
                        <span className="font-medium">{t.description}</span>
                        <TransactionSourceBadge source={t.source} />
                      </td>
                      <td
                        className={`font-figures p-4 font-bold whitespace-nowrap ${t.type === "income" ? "text-emerald-500" : "text-zinc-100"}`}
                      >
                        {t.type === "expense" ? "- " : "+ "}
                        {new Intl.NumberFormat("pt-BR", {
                          style: "currency",
                          currency: "BRL",
                        }).format(t.amount)}
                      </td>
                      <td className="p-4 text-zinc-400 text-sm">
                        <span className="bg-zinc-800 px-2 py-1 rounded-md whitespace-nowrap">
                          {t.category}
                        </span>
                      </td>
                      <td className="p-4 text-right text-zinc-500 text-sm whitespace-nowrap">
                        {formatTransactionDate(t.date)}
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-3">
                          {t.has_attachment && (
                            <button
                              onClick={() => void handleViewAttachment(t)}
                              disabled={viewingAttachmentId === t.id}
                              className="flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-sky-400 hover:text-sky-300 disabled:opacity-50"
                            >
                              <FileSearch size={14} />
                              {viewingAttachmentId === t.id ? "Abrindo..." : "Mostrar comprovante"}
                            </button>
                          )}
                          <button
                            onClick={() => window.dispatchEvent(new CustomEvent("open-transaction-modal", { detail: t }))}
                            aria-label={`Editar transação ${t.description}`}
                            className="text-zinc-600 hover:text-emerald-500 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(t)}
                            disabled={deletingId === t.id}
                            aria-label={`Excluir transação ${t.description}`}
                            className="text-zinc-600 hover:text-rose-500 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100 disabled:opacity-50"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
    <StatementImportDialog
      open={importOpen}
      onClose={() => setImportOpen(false)}
      onImported={fetchTransactions}
    />
    </AppLayout>
  );
}

function transactionSourceFilter(
  source: Transaction["source"],
): SourceFilter | "whatsapp" {
  if (
    source === "import" ||
    source === "import_csv" ||
    source === "import_pdf" ||
    source === "import_image"
  ) return "import";
  if (
    source === "whatsapp_text" ||
    source === "whatsapp_audio" ||
    source === "whatsapp_image" ||
    source === "whatsapp_document"
  ) {
    return "whatsapp";
  }
  return "manual";
}

function TransactionSourceBadge({
  source,
  mobile = false,
}: {
  source: Transaction["source"];
  mobile?: boolean;
}) {
  const labels: Record<NonNullable<Transaction["source"]>, string> = {
    manual: "Manual",
    dashboard_manual: "Manual",
    web: "Manual",
    import: "Importada",
    import_csv: "Extrato importado",
    import_pdf: "Extrato importado",
    import_image: "Extrato importado",
    whatsapp_text: "WhatsApp texto",
    whatsapp_audio: "WhatsApp áudio",
    whatsapp_image: "WhatsApp comprovante",
    whatsapp_document: "WhatsApp comprovante",
  };
  const normalizedSource = source ?? "manual";
  const isImport = normalizedSource.startsWith("import");
  const isWhatsApp = normalizedSource.startsWith("whatsapp_");

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs shrink-0 ${
        mobile ? "ml-1.5 mt-1" : ""
      } ${
        isImport
          ? "bg-sky-500/10 text-sky-400"
          : isWhatsApp
            ? "bg-emerald-500/10 text-emerald-400"
            : "bg-zinc-800 text-zinc-400"
      }`}
    >
      {isImport && <UploadCloud size={10} />}
      {labels[normalizedSource]}
    </span>
  );
}

function formatTransactionDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return `${day}/${month}/${year}`;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
