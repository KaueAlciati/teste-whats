"use client";
import { useState } from "react";
import { Calendar, CheckCircle2, Trash2, PlusCircle } from "lucide-react";
import { storage } from "@/lib/storage";
import { formatCurrency } from "@/lib/utils";
import type { Goal } from "@/lib/api";
import { AddValueModal } from "./AddValueModal";
import { useToast } from "@/contexts/ToastContext";

interface GoalCardProps {
  goal: Goal;
  onUpdate: () => void;
}

export function GoalCard({ goal, onUpdate }: GoalCardProps) {
  const [isAddValueOpen, setIsAddValueOpen] = useState(false);
  const { addToast } = useToast();
  const isCompleted = goal.completed || goal.percent >= 100;

  async function handleComplete() {
    try {
      await storage.completeGoal(goal.id);
      onUpdate();
    } catch (err) {
      console.error(err);
      addToast("error", "Não foi possível concluir a meta agora. Tente novamente.");
    }
  }

  async function handleDelete() {
    if (
      confirm(
        `Excluir a meta "${goal.goal_name}" (alvo: ${formatCurrency(goal.target)})?\n\nEssa ação não pode ser desfeita.`,
      )
    ) {
      try {
        await storage.deleteGoal(goal.id);
        onUpdate();
      } catch (err) {
        console.error(err);
        addToast("error", "Não foi possível excluir a meta agora. Tente novamente.");
      }
    }
  }

  return (
    <div className={`bg-zinc-900 border rounded-2xl p-6 transition-all relative group ${
      isCompleted ? 'border-emerald-500/30' : 'border-zinc-800 hover:border-zinc-700'
    }`}>
      {/* Topo */}
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-bold text-white">
              {goal.goal_name}
            </h3>
            {isCompleted && (
              <span className="bg-emerald-500/10 text-emerald-500 text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md border border-emerald-500/20">
                Concluída
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-zinc-500 text-sm mt-1">
            <span>Objetivo:{" "}
              {new Intl.NumberFormat("pt-BR", {
                style: "currency",
                currency: "BRL",
              }).format(goal.target)}
            </span>
            {goal.deadline && (
              <>
                <span className="text-zinc-700">•</span>
                <span className="flex items-center gap-1">
                  <Calendar size={14} />
                  {new Date(goal.deadline).toLocaleDateString('pt-BR')}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="text-right flex flex-col items-end gap-2">
          <div>
            <p className={`font-figures text-2xl font-bold ${isCompleted ? 'text-emerald-500' : 'text-emerald-400'}`}>
              {Math.min(goal.percent, 100).toFixed(0)}%
            </p>
            <p className="text-zinc-500 text-xs">concluído</p>
          </div>
          
          {/* Sempre visível no toque (abaixo de md); no desktop some até
              passar o mouse no card, igual antes. */}
          <div className="flex gap-1 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
            {!isCompleted && (
              <>
                <button 
                  onClick={() => setIsAddValueOpen(true)}
                  aria-label="Adicionar valor"
                  className="p-2 hover:bg-emerald-500/10 hover:text-emerald-500 text-zinc-500 rounded-lg transition-colors flex items-center gap-1 text-xs font-bold"
                  title="Adicionar valor"
                >
                  <PlusCircle size={18} />
                </button>
                <button 
                  onClick={handleComplete}
                  aria-label="Concluir meta"
                  className="p-2 hover:bg-emerald-500/10 hover:text-emerald-500 text-zinc-500 rounded-lg transition-colors"
                  title="Concluir meta"
                >
                  <CheckCircle2 size={18} />
                </button>
              </>
            )}
            <button 
              onClick={handleDelete}
              aria-label="Excluir meta"
              className="p-2 hover:bg-rose-500/10 hover:text-rose-500 text-zinc-500 rounded-lg transition-colors"
              title="Excluir meta"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Barra */}
      <div className="w-full bg-zinc-800 h-3 rounded-full mt-5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-1000 ease-out ${
            isCompleted ? 'bg-emerald-500' : 'bg-emerald-500'
          }`}
          style={{
            width: `${Math.min(goal.percent, 100)}%`,
          }}
        />
      </div>

      {/* Valores */}
      <div className="grid grid-cols-2 gap-4 mt-5">
        <div className="bg-zinc-800/50 rounded-xl p-4">
          <p className="text-zinc-500 text-xs uppercase font-bold tracking-wider">Guardado</p>

          <p className="font-figures text-lg font-bold text-white mt-1">
            {new Intl.NumberFormat("pt-BR", {
              style: "currency",
              currency: "BRL",
            }).format(goal.current)}
          </p>
        </div>

        <div className="bg-zinc-800/50 rounded-xl p-4">
          <p className="text-zinc-500 text-xs uppercase font-bold tracking-wider">
            {isCompleted ? "Excedente" : "Falta"}
          </p>

          <p className="font-figures text-lg font-bold text-white mt-1">
            {new Intl.NumberFormat("pt-BR", {
              style: "currency",
              currency: "BRL",
            }).format(Math.abs(goal.missing))}
          </p>
        </div>
      </div>

      {/* Motivação / Status */}
      <div className={`mt-4 p-3 rounded-xl transition-colors ${
        isCompleted ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-zinc-800/60 border border-zinc-700/50'
      }`}>
        {isCompleted ? (
          <div className="flex items-center justify-between">
            <p className="text-emerald-400 text-sm font-bold flex items-center gap-2">
              <CheckCircle2 size={16} />
              Meta alcançada!
            </p>
            <span className="text-[10px] text-emerald-500/60 font-black uppercase">Finalizado</span>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-zinc-300 text-sm">
              Faltam <span className="font-figures text-emerald-400 font-bold">{new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(goal.missing)}</span>
            </p>
            <button 
              onClick={() => setIsAddValueOpen(true)}
              className="text-[10px] font-black uppercase tracking-widest text-emerald-500 hover:text-emerald-400 transition-colors"
            >
              <PlusCircle size={14} className="inline mr-1" />
              Aportar
            </button>
          </div>
        )}
      </div>

      {!isCompleted && (
        <AddValueModal 
          goalId={goal.id}
          goalName={goal.goal_name}
          isOpen={isAddValueOpen}
          onClose={() => setIsAddValueOpen(false)}
          onSuccess={onUpdate}
        />
      )}
    </div>
  );
}
