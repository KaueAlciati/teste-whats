"use client";
import { useEffect, useState } from "react";
import { X, DollarSign, Plus } from "lucide-react";
import { storage } from "@/lib/storage";
import { useToast } from "@/contexts/ToastContext";

interface AddValueModalProps {
  goalId: number;
  goalName: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function AddValueModal({ goalId, goalName, isOpen, onClose, onSuccess }: AddValueModalProps) {
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) return;

    setLoading(true);
    try {
      await storage.depositGoal(goalId, parseFloat(amount));
      setAmount("");
      onSuccess();
      onClose();
    } catch (err) {
      console.error("Erro ao adicionar valor:", err);
      addToast("error", "Não foi possível adicionar o valor agora. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-value-modal-title"
        className="bg-zinc-900 border border-zinc-800 w-full max-w-sm rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl max-h-[90dvh] overflow-y-auto"
        style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}
      >
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 id="add-value-modal-title" className="text-xl font-bold text-white">Adicionar Valor</h2>
            <p className="text-zinc-500 text-xs mt-1">{goalName}</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="flex h-9 w-9 items-center justify-center -mr-2 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs text-zinc-500 uppercase font-bold block ml-1">
              Quanto você guardou?
            </label>
            <div className="relative">
              <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={18} />
              <input
                type="number"
                step="0.01"
                placeholder="0,00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="font-figures w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-emerald-500 transition-all text-white font-bold"
                required
                autoFocus
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !amount}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 py-3 rounded-lg font-bold text-sm transition-all flex items-center justify-center gap-2"
          >
            {loading ? "Salvando..." : (
              <>
                <Plus size={18} />
                Confirmar Aporte
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
