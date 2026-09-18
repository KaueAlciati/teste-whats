"use client";
import { useEffect, useState } from "react";
import { X, Target } from "lucide-react";
import { storage } from "@/lib/storage";
import { useToast } from "@/contexts/ToastContext";

interface NewGoalModalProps {
  onSuccess?: () => void;
}

export function NewGoalModal({ onSuccess }: NewGoalModalProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [deadline, setDeadline] = useState("");
  const [loading, setLoading] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setIsOpen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const newGoal = {
        name,
        target_amount: parseFloat(target),
        current_amount: 0,
        deadline,
      };

      await storage.createGoal(newGoal);
      
      setIsOpen(false);
      setName("");
      setTarget("");
      setDeadline("");
      
      if (onSuccess) onSuccess();
    } catch (err) {
      console.error("Erro ao criar meta:", err);
      addToast("error", "Não foi possível criar a meta agora. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen)
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors w-full sm:w-auto"
      >
        <Target size={18} /> Nova Meta
      </button>
    );

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-goal-modal-title"
        className="bg-zinc-900 border border-zinc-800 w-full max-w-md rounded-t-2xl sm:rounded-2xl p-6 max-h-[90dvh] overflow-y-auto"
        style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}
      >
        <div className="flex justify-between items-center mb-6">
          <h2 id="new-goal-modal-title" className="text-xl font-bold">Definir Nova Meta</h2>
          <button
            onClick={() => setIsOpen(false)}
            aria-label="Fechar"
            className="flex h-9 w-9 items-center justify-center -mr-2 text-zinc-500 hover:text-zinc-300"
          >
            <X size={20} />
          </button>
        </div>
        <form onSubmit={handleSave} className="space-y-4">
          <input
            type="text"
            placeholder="Nome da meta (ex: Reserva de Emergência)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all"
            required
          />
          <div className="grid grid-cols-2 gap-4">
            <input
              type="number"
              placeholder="Valor Alvo"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="font-figures w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm focus:outline-none focus:border-emerald-500 transition-all"
              required
            />
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-zinc-400 text-sm focus:outline-none focus:border-emerald-500 transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 hover:bg-emerald-500 py-3 rounded-lg font-bold transition-all disabled:opacity-50"
          >
            {loading ? "Criando..." : "Criar Meta"}
          </button>
        </form>
      </div>
    </div>
  );
}
