"use client";

import { useEffect, useState, useCallback } from "react";
import { NewGoalModal } from "@/components/NewGoalModal";
import { GoalCard } from "@/components/GoalCard";
import { storage } from "@/lib/storage";
import type { Goal } from "@/lib/api";
import { Search, CheckCircle2 } from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";

export default function PlanningPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "completed">("all");
  const handleFetchError = useHandleFetchError();

  const loadGoals = useCallback(async () => {
    try {
      setLoading(true);
      const data = await storage.getGoalsStatus();
      setGoals(data);
    } catch (err) {
      await handleFetchError(err, "Erro ao carregar metas:");
    } finally {
      setLoading(false);
    }
  }, [handleFetchError]);

  useEffect(() => {
    loadGoals();
  }, [loadGoals]);

  const filteredGoals = goals.filter((goal) => {
    const matchesSearch = goal.goal_name.toLowerCase().includes(searchTerm.toLowerCase());
    if (filter === "active") return matchesSearch && goal.percent < 100;
    if (filter === "completed") return matchesSearch && goal.percent >= 100;
    return matchesSearch;
  });

  return (
    <AppLayout>
      <div className="min-h-screen">
      {/* Header — empilha no mobile (senão "Planejamento" + o botão
          "Nova Meta" espremiam um contra o outro numa tela estreita) */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold">Planejamento</h1>

          <p className="text-zinc-500 text-sm mt-1">
            Acompanhe suas metas financeiras
          </p>
        </div>

        <NewGoalModal onSuccess={loadGoals} />
      </div>

      {/* Resumo */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <p className="text-zinc-500 text-sm">Total Guardado</p>

          <h2 className="font-figures text-2xl font-bold mt-2 text-emerald-400">
            {new Intl.NumberFormat("pt-BR", {
              style: "currency",
              currency: "BRL",
            }).format(goals.reduce((acc, goal) => acc + goal.current, 0))}
          </h2>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <p className="text-zinc-500 text-sm">Metas Ativas</p>

          <h2 className="font-figures text-2xl font-bold mt-2">{goals.filter(g => g.percent < 100).length}</h2>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
          <p className="text-zinc-500 text-sm">Meta Mais Próxima</p>

          <h2 className="text-lg font-bold mt-2 text-emerald-400 truncate">
            {goals.length > 0
              ? [...goals].sort((a, b) => b.percent - a.percent)[0].goal_name
              : "Nenhuma"}
          </h2>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-4 justify-between items-center mb-6">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
          <input 
            type="text" 
            placeholder="Buscar metas..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:border-emerald-500 transition-all"
          />
        </div>
        
        <div className="flex gap-2 p-1 bg-zinc-900 border border-zinc-800 rounded-lg">
          {(['all', 'active', 'completed'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                filter === f 
                  ? 'bg-zinc-800 text-emerald-400' 
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {f === 'all' ? 'Todas' : f === 'active' ? 'Ativas' : 'Concluídas'}
            </button>
          ))}
        </div>
      </div>

      {/* Lista de metas */}
      <div className="space-y-10">
        {/* Metas em Andamento */}
        <section>
          <div className="grid gap-5">
            {loading ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center animate-pulse">
                <p className="text-zinc-500">Carregando metas...</p>
              </div>
            ) : filteredGoals.filter(g => g.percent < 100).length === 0 ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center border-dashed">
                <p className="text-zinc-500 text-sm">Nenhuma meta ativa no momento.</p>
              </div>
            ) : (
              filteredGoals.filter(g => g.percent < 100).map((goal) => (
                <GoalCard key={goal.id} goal={goal} onUpdate={loadGoals} />
              ))
            )}
          </div>
        </section>

        {/* Metas Concluídas */}
        {filteredGoals.some(g => g.percent >= 100) && (
          <section>
            <h2 className="text-lg font-bold mb-4 flex items-center gap-2 text-zinc-500">
              <CheckCircle2 className="text-emerald-500" size={18} />
              Concluídas
            </h2>
            <div className="grid gap-5 opacity-80">
              {filteredGoals.filter(g => g.percent >= 100).map((goal) => (
                <GoalCard key={goal.id} goal={goal} onUpdate={loadGoals} />
              ))}
            </div>
          </section>
        )}
      </div>
      </div>
    </AppLayout>
  );
}
