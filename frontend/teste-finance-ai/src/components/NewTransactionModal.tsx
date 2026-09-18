"use client";

import { useEffect, useRef, useState } from "react";
import { X, Plus } from "lucide-react";
import { storage } from "@/lib/storage";
import type { Transaction } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useToast } from "@/contexts/ToastContext";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { formatCategoryLabel } from "@/lib/category";

function todayDateInputValue() {
  return new Date().toISOString().slice(0, 10);
}

export function NewTransactionModal() {
  const router = useRouter();
  const { addToast } = useToast();
  const handleFetchError = useHandleFetchError();

  const [isOpen, setIsOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [type, setType] = useState("income");
  const [category, setCategory] = useState("");
  const [date, setDate] = useState(todayDateInputValue());
  const [loading, setLoading] = useState(false);

  const descriptionInputRef = useRef<HTMLInputElement>(null);

  // Qualquer lista (Dashboard, Extrato) pode disparar este evento com
  // os dados de uma transação existente para abrir o mesmo formulário
  // em modo de edição, sem precisar duplicar o modal em cada tela.
  useEffect(() => {
    function handleOpenForEdit(e: Event) {
      const transaction = (e as CustomEvent<Transaction>).detail;
      setEditingId(transaction.id ?? null);
      setDescription(transaction.description);
      setAmount(String(transaction.amount));
      setType(transaction.type);
      setCategory(transaction.category);
      setDate(transaction.date ? transaction.date.slice(0, 10) : todayDateInputValue());
      setIsOpen(true);
    }

    window.addEventListener("open-transaction-modal", handleOpenForEdit);
    return () => window.removeEventListener("open-transaction-modal", handleOpenForEdit);
  }, []);

  // Fecha com Esc, e foca o primeiro campo assim que o modal abre —
  // sem isso, quem usa teclado/leitor de tela cai direto no formulário
  // sem saber onde o foco está.
  useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(() => descriptionInputRef.current?.focus(), 50);

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closeModal();
    }
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function openForNew() {
    setEditingId(null);
    setDescription("");
    setAmount("");
    setCategory("");
    setType("income");
    setDate(todayDateInputValue());
    setIsOpen(true);
  }

  function closeModal() {
    setIsOpen(false);
    setEditingId(null);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();

    const parsedAmount = parseFloat(amount);
    if (!parsedAmount || parsedAmount <= 0) {
      addToast("error", "Informe um valor maior que zero.");
      return;
    }

    setLoading(true);

    const transactionData = {
      description,
      amount: parsedAmount,
      type: type as "income" | "expense",
      // Mesma capitalização amigável aplicada pelo backend
      // (app/schemas/finance.py) — mantém API e LocalStorage
      // consistentes, sem depender de qual modo está ativo.
      category: formatCategoryLabel(category),
      date,
    };

    try {
      if (editingId) {
        await storage.updateTransaction(editingId, transactionData);
        addToast("success", "Transação atualizada!");
      } else {
        await storage.createTransaction(transactionData);
        addToast("success", "Transação adicionada!");
      }

      closeModal();
      setDescription("");
      setAmount("");
      setCategory("");
      setType("income");
      setDate(todayDateInputValue());

      // Recarrega os dados sem reload total da página se possível
      router.refresh();
      // Nome genérico: qualquer mudança em transações (criar, editar,
      // excluir) dispara o mesmo evento, e qualquer tela que dependa
      // desses dados (resumo do dashboard, insights, extrato) escuta
      // este único evento para se manter sincronizada.
      window.dispatchEvent(new Event("transactions-changed"));
    } catch (error) {
      await handleFetchError(error, "Erro ao salvar transação:");
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) {
    return (
      <button
        onClick={openForNew}
        className="fixed right-5 bottom-5 sm:right-8 sm:bottom-8 flex items-center justify-center w-14 h-14 sm:w-auto sm:h-auto sm:justify-start sm:px-6 sm:py-4 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600 text-white font-semibold shadow-[0_10px_20px_rgba(27,175,128,0.25)] ring-1 ring-white/20 hover:shadow-[0_15px_30px_rgba(27,175,128,0.4)] hover:-translate-y-1 active:scale-95 transition-all duration-300 ease-out group z-40 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
        style={{ marginBottom: "env(safe-area-inset-bottom)", marginRight: "env(safe-area-inset-right)" }}
        aria-label="Nova transação"
        title="Nova transação"
      >
        <Plus size={22} className="shrink-0 group-hover:rotate-90 transition-transform duration-300" />

        {/* Só desktop: em toque não existe estado de hover real, então
            manter o rótulo escondido também no mobile evitava um "salto"
            de layout ao tocar e — pelo gap do flex ficar reservado mesmo
            com o texto de largura zero — descentralizava o ícone dentro
            do botão redondo. */}
        <span className="hidden sm:block max-w-0 overflow-hidden group-hover:max-w-xs group-hover:ml-2 transition-all duration-500 ease-in-out whitespace-nowrap tracking-tight">
          Nova Transação
        </span>
      </button>
    );
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-end justify-center sm:items-center sm:p-4"
      onMouseDown={(e) => {
        // Fecha ao clicar fora da caixa do modal (no overlay escuro)
        if (e.target === e.currentTarget) closeModal();
      }}
    >
      {/* No celular vira uma "bottom sheet" (colada na base, sem raio
          embaixo, rolável) em vez de uma caixa centralizada — fica mais
          fácil de alcançar com o polegar e evita cortar o formulário
          quando o teclado abre. A partir de sm: volta a ser um modal
          centralizado normal. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="transaction-modal-title"
        className="bg-zinc-900 border border-zinc-800 w-full max-w-md rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl max-h-[90dvh] overflow-y-auto"
        style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}
      >
        <div className="flex justify-between items-center mb-6">
          <h2 id="transaction-modal-title" className="text-xl font-bold">
            {editingId ? "Editar Transação" : "Adicionar Transação"}
          </h2>

          <button
            onClick={closeModal}
            aria-label="Fechar"
            className="flex h-9 w-9 items-center justify-center -mr-2 text-zinc-500 hover:text-zinc-300"
          >
            <X size={20} />
          </button>
        </div>

        <form className="space-y-4" onSubmit={handleSave}>
          <div>
            <label htmlFor="tx-description" className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
              Descrição
            </label>

            <input
              ref={descriptionInputRef}
              id="tx-description"
              type="text"
              placeholder="Ex: Salário, Netflix..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all"
              required
              maxLength={120}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="tx-amount" className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                Valor
              </label>

              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-zinc-500 pointer-events-none">
                  R$
                </span>
                <input
                  id="tx-amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0,00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="font-figures w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 pl-9 text-sm focus:outline-none focus:border-emerald-500 transition-all"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="tx-type" className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                Tipo
              </label>

              <select
                id="tx-type"
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all"
              >
                <option value="income">Entrada</option>
                <option value="expense">Saída</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="tx-category" className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                Categoria
              </label>

              <input
                id="tx-category"
                type="text"
                placeholder="Ex: Lazer, Moradia..."
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all"
                required
                maxLength={60}
              />
            </div>

            <div>
              <label htmlFor="tx-date" className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                Data
              </label>

              <input
                id="tx-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                max={todayDateInputValue()}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all [color-scheme:dark]"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 hover:bg-emerald-500 py-3 rounded-lg font-bold text-sm transition-colors mt-4 disabled:opacity-50"
          >
            {loading ? "Salvando..." : editingId ? "Salvar Alterações" : "Salvar Transação"}
          </button>
        </form>
      </div>
    </div>
  );
}
