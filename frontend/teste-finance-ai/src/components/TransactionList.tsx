"use client";

import { useEffect, useState, useCallback } from "react";
import { ArrowUpCircle, ArrowDownCircle, Receipt, Trash2, Pencil } from "lucide-react";
import { storage } from "@/lib/storage";
import type { Transaction } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export function TransactionList() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadTransactions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await storage.getTransactions();
      setTransactions(data);
    } catch (err) {
      console.error("Erro ao carregar transações:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTransactions();

    // Escuta o evento disparado ao criar OU excluir uma transação,
    // em qualquer parte do app, para manter esta lista sincronizada.
    window.addEventListener("transactions-changed", loadTransactions);
    return () => window.removeEventListener("transactions-changed", loadTransactions);
  }, [loadTransactions]);

  async function handleDelete(transaction: Transaction) {
    if (!transaction.id) return;

    // Mostrar o valor formatado, e não só a descrição, reduz o risco
    // de excluir a transação errada quando duas têm nomes parecidos
    // (ex: duas entradas de "Salário" em meses diferentes) — ver
    // docs/IDEIAS.md.
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
      console.error("Erro ao excluir transação:", err);
      alert("Não foi possível excluir a transação. Tente novamente.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6">
      <div className="flex items-center gap-2 mb-6">
        <Receipt className="text-emerald-500" size={20} />
        <h2 className="text-lg font-bold">Transações Recentes</h2>
      </div>

      <div className="space-y-4">
        {loading ? (
          [1, 2, 3, 4].map((i) => (
            <div key={i} className="flex justify-between items-center border-b border-zinc-800/50 pb-3 last:border-0 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-zinc-800 rounded-full"></div>
                <div className="space-y-2">
                  <div className="h-4 bg-zinc-800 rounded w-24"></div>
                  <div className="h-3 bg-zinc-800 rounded w-16"></div>
                </div>
              </div>
              <div className="h-4 bg-zinc-800 rounded w-20"></div>
            </div>
          ))
        ) : transactions.length === 0 ? (
          <p className="text-zinc-500 text-sm text-center py-4">Nenhuma atividade recente.</p>
        ) : (
          transactions.slice(0, 5).map((t) => (
            <div
              key={t.id}
              className="group flex justify-between items-center border-b border-zinc-800/50 pb-3 last:border-0"
            >
              <div className="flex items-center gap-3 min-w-0">
                {t.type === "income" ? (
                  <ArrowUpCircle className="text-emerald-500 shrink-0" size={20} />
                ) : (
                  <ArrowDownCircle className="text-rose-500 shrink-0" size={20} />
                )}

                <div className="min-w-0">
                  <p className="text-sm font-medium text-white truncate">{t.description}</p>
                  <p className="text-xs text-zinc-500">{t.category}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <p
                  className={`font-figures text-sm font-bold ${
                    t.type === "income" ? "text-emerald-500" : "text-zinc-100"
                  }`}
                >
                  {t.type === "expense" ? "- " : "+ "}
                  {new Intl.NumberFormat("pt-BR", {
                    style: "currency",
                    currency: "BRL",
                  }).format(t.amount)}
                </p>

                {/* No touch (abaixo de md) os ícones ficam sempre visíveis —
                    "aparece só no hover" não existe em quem usa o dedo, o
                    botão simplesmente nunca aparecia nesses aparelhos. Do
                    md pra cima, mantém o hover-to-reveal (mais limpo no
                    desktop, onde o mouse dá esse sinal). Área de toque em
                    44x44 (abaixo de md) — WCAG recomenda esse mínimo, e os
                    32x32 anteriores ficavam justos ao lado um do outro
                    (editar bem colado no excluir, que é destrutivo). */}
                <button
                  onClick={() => window.dispatchEvent(new CustomEvent("open-transaction-modal", { detail: t }))}
                  aria-label={`Editar transação ${t.description}`}
                  className="flex h-11 w-11 md:h-8 md:w-8 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-emerald-500 transition-colors md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
                >
                  <Pencil size={16} />
                </button>

                <button
                  onClick={() => handleDelete(t)}
                  disabled={deletingId === t.id}
                  aria-label={`Excluir transação ${t.description}`}
                  className="flex h-11 w-11 md:h-8 md:w-8 items-center justify-center rounded-lg text-zinc-500 hover:bg-rose-500/10 hover:text-rose-500 transition-colors md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100 disabled:opacity-50"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
