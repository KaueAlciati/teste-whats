"use client";

import { useEffect, useState } from "react";
import { User, Sparkles, Database, ShieldAlert, Globe2 } from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { storage } from "@/lib/storage";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import type { UserSettings } from "@/lib/api";

function getInitials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

export default function SettingsPage() {
  const { user, logout, refreshUser } = useAuth();
  const { addToast } = useToast();
  const handleFetchError = useHandleFetchError();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);

  const [clearing, setClearing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
    }
  }, [user]);

  useEffect(() => {
    storage
      .getSettings()
      .then(setSettings)
      .catch((err) => handleFetchError(err, "Erro ao carregar configurações:"));
  }, [handleFetchError]);

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    try {
      await storage.updateProfile({ name, email });
      await refreshUser();
      addToast("success", "Perfil atualizado com sucesso!");
    } catch (err) {
      await handleFetchError(err, "Erro ao atualizar perfil:");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleToggle(key: "notifications_enabled" | "ai_enabled") {
    if (!settings) return;
    const next = { ...settings, [key]: !settings[key] };
    setSettings(next);
    setSavingSettings(true);
    try {
      const updated = await storage.updateSettings({ [key]: next[key] });
      setSettings(updated);
    } catch (err) {
      setSettings(settings);
      await handleFetchError(err, "Erro ao salvar preferência:");
    } finally {
      setSavingSettings(false);
    }
  }

  async function handleClearHistory() {
    if (!confirm("Isso vai apagar TODAS as suas transações. Essa ação não pode ser desfeita. Continuar?")) return;
    setClearing(true);
    try {
      const transactions = await storage.getTransactions();
      await Promise.all(
        transactions
          .filter((t) => t.id !== undefined)
          .map((t) => storage.deleteTransaction(t.id as number)),
      );
      window.dispatchEvent(new Event("transactions-changed"));
      addToast("success", "Histórico de transações apagado.");
    } catch (err) {
      await handleFetchError(err, "Erro ao limpar histórico:");
    } finally {
      setClearing(false);
    }
  }

  async function handleDeleteAccount() {
    if (
      !confirm(
        "Isso vai excluir sua conta e TODOS os seus dados (transações, metas, notificações) permanentemente. Essa ação não pode ser desfeita. Continuar?",
      )
    )
      return;
    setDeleting(true);
    try {
      await storage.deleteAccount();
      addToast("success", "Conta excluída.");
      await logout();
    } catch (err) {
      await handleFetchError(err, "Erro ao excluir conta:");
    } finally {
      setDeleting(false);
    }
  }

  const displayName = user?.name ?? "Usuário";
  const initials = getInitials(displayName);
  const memberSince = user?.created_at
    ? new Date(user.created_at).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "long",
        year: "numeric",
      })
    : null;

  return (
    <AppLayout>
      <main className="space-y-8">
        <header>
          <h1 className="text-2xl font-bold">Configurações</h1>
          <p className="text-zinc-400 text-sm">
            Gerencie seu perfil, preferências e dados da conta.
          </p>
        </header>

        <div className="max-w-4xl space-y-6">
          {/* Seção: Perfil */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-5">
            <div className="flex items-center gap-2 text-emerald-500">
              <User size={20} />
              <h3 className="font-bold">Perfil do Usuário</h3>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center gap-4 pb-1">
              <div className="w-16 h-16 shrink-0 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-xl font-bold text-white shadow-sm shadow-emerald-500/20 ring-1 ring-white/10">
                {initials}
              </div>
              <div className="min-w-0">
                <p className="text-base font-semibold text-zinc-100 truncate">
                  {displayName}
                </p>
                <p className="text-sm text-zinc-500 truncate">{user?.email}</p>
                {memberSince && (
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Membro desde {memberSince}
                  </p>
                )}
              </div>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                    Nome
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    minLength={2}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
                    E-mail
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={savingProfile}
                className="w-full sm:w-auto text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2.5 rounded-lg transition-colors font-medium"
              >
                {savingProfile ? "Salvando..." : "Salvar alterações"}
              </button>
            </form>
          </section>

          {/* Seção: Notificações e IA */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-4">
            <div className="flex items-center gap-2 text-ai-400">
              <Sparkles size={20} />
              <h3 className="font-bold">Notificações e IA</h3>
            </div>
            <div className="divide-y divide-zinc-800/70">
              {!settings ? (
                <div className="py-4 space-y-3" aria-hidden="true">
                  {[0, 1].map((i) => (
                    <div key={i} className="flex items-center justify-between gap-4 py-1">
                      <div className="space-y-2 flex-1">
                        <div className="h-4 w-40 bg-zinc-800 rounded animate-pulse" />
                        <div className="h-3 w-full max-w-xs bg-zinc-800/70 rounded animate-pulse" />
                      </div>
                      <div className="h-6 w-11 bg-zinc-800 rounded-full animate-pulse shrink-0" />
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <ToggleItem
                    title="Alertas de Gastos Críticos"
                    description="Receber aviso quando ultrapassar 80% do orçamento."
                    checked={settings?.notifications_enabled ?? true}
                    disabled={savingSettings}
                    onToggle={() => handleToggle("notifications_enabled")}
                  />
                  <ToggleItem
                    title="Insights de IA"
                    description="Permite que o Dashboard e a tela de Insights analisem seu histórico para gerar previsões e sugestões. Desligado, as duas telas param de gerar novas análises."
                    checked={settings?.ai_enabled ?? true}
                    disabled={savingSettings}
                    onToggle={() => handleToggle("ai_enabled")}
                  />
                </>
              )}
            </div>
          </section>

          {/* Seção: Preferências regionais — hoje só informativo. O
              backend já guarda currency/locale por usuário, mas nada no
              sistema formata valores de acordo com eles ainda (ver
              docs/IDEIAS.md, "Multi-moeda"): todo valor é exibido em
              BRL/pt-BR fixo. Mostrar como somente-leitura evita prometer
              uma opção que ainda não tem efeito real. */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-4">
            <div className="flex items-center gap-2 text-blue-400">
              <Globe2 size={20} />
              <h3 className="font-bold">Preferências Regionais</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">Moeda</p>
                <p className="text-sm text-zinc-300 mt-0.5">Real (R$)</p>
              </div>
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">Idioma</p>
                <p className="text-sm text-zinc-300 mt-0.5">Português (Brasil)</p>
              </div>
            </div>
            <p className="text-xs text-zinc-500">
              Suporte a múltiplas moedas e idiomas está no radar — por enquanto, todo valor é exibido em BRL.
            </p>
          </section>

          {/* Seção: Dados — separada visualmente das demais (fundo com
              tom de risco) porque as duas ações aqui são destrutivas e
              irreversíveis; misturar com o resto convidava a um clique
              apressado. */}
          <section className="p-5 sm:p-6 rounded-2xl border border-rose-500/20 bg-rose-500/[0.04] space-y-4">
            <div className="flex items-center gap-2 text-rose-500">
              <ShieldAlert size={20} />
              <h3 className="font-bold">Zona de Risco</h3>
            </div>
            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 rounded-xl bg-zinc-950/60 border border-zinc-800">
                <div className="flex items-center gap-3 min-w-0">
                  <Database size={18} className="text-zinc-500 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-200">Limpar histórico</p>
                    <p className="text-xs text-zinc-500">Apaga todas as transações, sem excluir a conta.</p>
                  </div>
                </div>
                <button
                  onClick={handleClearHistory}
                  disabled={clearing}
                  className="w-full sm:w-auto shrink-0 text-sm bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors"
                >
                  {clearing ? "Limpando..." : "Limpar Histórico"}
                </button>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 rounded-xl bg-zinc-950/60 border border-rose-500/20">
                <div className="flex items-center gap-3 min-w-0">
                  <ShieldAlert size={18} className="text-rose-500/80 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-200">Excluir conta</p>
                    <p className="text-xs text-zinc-500">Remove permanentemente conta, transações, metas e notificações.</p>
                  </div>
                </div>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleting}
                  className="w-full sm:w-auto shrink-0 text-sm text-rose-500 border border-rose-500/30 hover:bg-rose-500/10 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors"
                >
                  {deleting ? "Excluindo..." : "Excluir Conta"}
                </button>
              </div>
            </div>
          </section>
        </div>
      </main>
    </AppLayout>
  );
}

function ToggleItem({
  title,
  description,
  checked,
  disabled,
  onToggle,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center justify-between py-3.5 gap-4 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-zinc-200">{title}</p>
        <p className="text-xs text-zinc-500 leading-relaxed mt-0.5">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={title}
        disabled={disabled}
        onClick={onToggle}
        className={`relative shrink-0 w-12 h-7 rounded-full flex items-center px-1 transition-colors disabled:opacity-50 ${
          checked ? "bg-emerald-600 justify-end" : "bg-zinc-700 justify-start"
        }`}
      >
        <div className="w-5 h-5 bg-white rounded-full shadow-sm transition-transform" />
      </button>
    </div>
  );
}
