"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowUpCircle, ArrowDownCircle, Search, Trash2, Pencil, Download, UploadCloud, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { storage } from "@/lib/storage";
import type { Transaction } from "@/lib/api";
import { AppLayout } from "@/components/AppLayout";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { useToast } from "@/contexts/ToastContext";
import { downloadTransactionsCsv } from "@/lib/csv";
import { formatCurrency } from "@/lib/utils";
import { formatCategoryLabel, normalizeCategoryKey } from "@/lib/category";

type SourceFilter = "all" | "manual" | "import";

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
        // Transações antigas (criadas antes do campo `source` existir)
        // ou vindas do modo local não têm essa informação — tratamos
        // como "manual", que é o comportamento padrão de sempre.
        const source = t.source ?? "manual";
        return source === sourceFilter;
      })
      .filter((t) => categoryFilter === "all" || normalizeCategoryKey(t.category) === categoryFilter)
      .filter((t) => !dateFrom || t.date.slice(0, 10) >= dateFrom)
      .filter((t) => !dateTo || t.date.slice(0, 10) <= dateTo);
    setFilteredTransactions(filtered);
  }, [search, sourceFilter, categoryFilter, dateFrom, dateTo, transactions]);

  function handleExport() {
    if (filteredTransactions.length === 0) {
      addToast("error", "Não há transações para exportar.");
      return;
    }
    downloadTransactionsCsv(filteredTransactions);
    addToast("success", "Extrato exportado em CSV.");
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

          {/* Exportar CSV — sozinho, sem texto, já é um alvo de toque
              confortável (44x44px) e não briga por espaço com a busca
              em telas estreitas; o rótulo só aparece a partir de "sm". */}
          <button
            onClick={handleExport}
            aria-label="Exportar extrato em CSV"
            title="Exportar extrato em CSV"
            className="shrink-0 flex items-center justify-center gap-2 h-[42px] w-[42px] sm:w-auto sm:px-4 rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-emerald-500/40 hover:text-emerald-400 active:scale-95 transition-all text-sm font-medium"
          >
            <Download size={18} />
            <span className="hidden sm:inline">Exportar CSV</span>
          </button>

          <Link
            href="/transactions/import"
            aria-label="Importar extrato bancário"
            title="Importar extrato bancário"
            className="shrink-0 flex items-center justify-center gap-2 h-[42px] w-[42px] sm:w-auto sm:px-4 rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-300 hover:border-emerald-500/40 hover:text-emerald-400 active:scale-95 transition-all text-sm font-medium"
          >
            <UploadCloud size={18} />
            <span className="hidden sm:inline">Importar extrato</span>
          </Link>
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
                      {t.source === "import" && (
                        <span className="inline-flex items-center gap-1 ml-1.5 mt-1 bg-sky-500/10 text-sky-400 px-2 py-0.5 rounded-md text-xs">
                          <UploadCloud size={10} />
                          Importada
                        </span>
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
                    {new Date(t.date).toLocaleDateString("pt-BR")}
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
              <table className="w-full min-w-[620px] text-left border-collapse">
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
                        {t.source === "import" && (
                          <span className="inline-flex items-center gap-1 bg-sky-500/10 text-sky-400 px-2 py-0.5 rounded-md text-xs shrink-0">
                            <UploadCloud size={10} />
                            Importada
                          </span>
                        )}
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
                        {new Date(t.date).toLocaleDateString("pt-BR")}
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-3">
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
    </AppLayout>
  );
}
