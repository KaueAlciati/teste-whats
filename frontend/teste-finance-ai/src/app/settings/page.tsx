"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  User,
  Sparkles,
  Database,
  ShieldAlert,
  Globe2,
  LockKeyhole,
  LogOut,
} from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { api, HttpError } from "@/lib/api";
import {
  formatWhatsappPhone,
  logoutAndRedirect,
  REGIONAL_PREFERENCES,
} from "@/lib/settings-flow";

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
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const [clearing, setClearing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
    }
  }, [user]);

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    try {
      await api.updateProfile({ name, email });
      await refreshUser();
      addToast("success", "Perfil atualizado com sucesso!");
    } catch (err) {
      const detail = getErrorDetail(err);
      if (detail) addToast("error", detail);
      else await handleFetchError(err, "Erro ao atualizar perfil:");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmNewPassword) {
      addToast("error", "A confirmação da nova senha não confere.");
      return;
    }
    setSavingPassword(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      addToast("success", "Senha alterada com sucesso!");
    } catch (err) {
      const detail = getErrorDetail(err);
      if (detail) addToast("error", detail);
      else await handleFetchError(err, "Erro ao alterar senha:");
    } finally {
      setSavingPassword(false);
    }
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logoutAndRedirect(logout, (path) => router.replace(path));
    } finally {
      setLoggingOut(false);
    }
  }

  async function handleClearHistory() {
    const confirmation = window.prompt(
      'Esta ação apaga transações, metas e aportes. Digite "LIMPAR HISTÓRICO" para confirmar.',
    );
    if (confirmation !== "LIMPAR HISTÓRICO") return;
    setClearing(true);
    try {
      await api.clearFinancialHistory(confirmation);
      window.dispatchEvent(new Event("transactions-changed"));
      addToast("success", "Histórico financeiro apagado.");
    } catch (err) {
      await handleFetchError(err, "Erro ao limpar histórico:");
    } finally {
      setClearing(false);
    }
  }

  async function handleDeleteAccount() {
    const confirmation = window.prompt(
      'Esta ação é permanente. Digite "EXCLUIR CONTA" para confirmar.',
    );
    if (confirmation !== "EXCLUIR CONTA") return;
    setDeleting(true);
    try {
      await api.deleteAccount(confirmation);
      addToast("success", "Conta excluída.");
      await logoutAndRedirect(logout, (path) => router.replace(path));
    } catch (err) {
      await handleFetchError(err, "Erro ao excluir conta:");
    } finally {
      setDeleting(false);
    }
  }

  const displayName = user?.name ?? "Usuário";
  const initials = getInitials(displayName);
  const formattedWhatsapp = formatWhatsappPhone(user?.whatsapp_phone);
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

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">WhatsApp</p>
                <p className="text-sm text-zinc-300 mt-0.5">{formattedWhatsapp}</p>
              </div>
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">Status do WhatsApp</p>
                <p
                  className={`text-sm mt-0.5 font-medium ${
                    user?.whatsapp_verified ? "text-emerald-400" : "text-amber-400"
                  }`}
                >
                  {user?.whatsapp_verified ? "Conectado" : "Pendente"}
                </p>
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

          {/* Seção: Senha */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-5">
            <div className="flex items-center gap-2 text-amber-400">
              <LockKeyhole size={20} />
              <h3 className="font-bold">Alterar Senha</h3>
            </div>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <PasswordField
                  label="Senha atual"
                  value={currentPassword}
                  onChange={setCurrentPassword}
                />
                <PasswordField
                  label="Nova senha"
                  value={newPassword}
                  onChange={setNewPassword}
                  minLength={8}
                />
                <PasswordField
                  label="Confirmar nova senha"
                  value={confirmNewPassword}
                  onChange={setConfirmNewPassword}
                  minLength={8}
                />
              </div>
              <button
                type="submit"
                disabled={savingPassword}
                className="w-full sm:w-auto text-sm bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-4 py-2.5 rounded-lg transition-colors font-medium"
              >
                {savingPassword ? "Alterando..." : "Alterar senha"}
              </button>
            </form>
          </section>

          {/* Seção: Sessão */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-4">
            <div className="flex items-center gap-2 text-zinc-300">
              <LogOut size={20} />
              <h3 className="font-bold">Sessão</h3>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <p className="text-sm text-zinc-500">
                Encerre o acesso deste dispositivo com segurança.
              </p>
              <button
                type="button"
                onClick={handleLogout}
                disabled={loggingOut}
                className="w-full sm:w-auto text-sm bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 px-4 py-2.5 rounded-lg transition-colors font-medium"
              >
                {loggingOut ? "Saindo..." : "Sair da conta"}
              </button>
            </div>
          </section>

          {/* Seção: Notificações e IA */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-4">
            <div className="flex items-center gap-2 text-ai-400">
              <Sparkles size={20} />
              <h3 className="font-bold">Notificações e IA</h3>
            </div>
            <div className="divide-y divide-zinc-800/70">
              <ToggleItem
                title="Alertas de Gastos Críticos"
                description="Configuração disponível futuramente."
                checked={false}
                disabled
              />
              <ToggleItem
                title="Preferências de IA"
                description="Configuração disponível futuramente."
                checked={false}
                disabled
              />
            </div>
          </section>

          {/* Preferências regionais informativas enquanto não há persistência
              própria no backend. */}
          <section className="p-5 sm:p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 space-y-4">
            <div className="flex items-center gap-2 text-blue-400">
              <Globe2 size={20} />
              <h3 className="font-bold">Preferências Regionais</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">Moeda</p>
                <p className="text-sm text-zinc-300 mt-0.5">
                  Real ({REGIONAL_PREFERENCES.currency})
                </p>
              </div>
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-3">
                <p className="text-[11px] text-zinc-500 uppercase font-bold">Idioma</p>
                <p className="text-sm text-zinc-300 mt-0.5">
                  Português (Brasil) · {REGIONAL_PREFERENCES.locale}
                </p>
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
                    <p className="text-xs text-zinc-500">Apaga transações, metas e aportes, sem excluir a conta.</p>
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
  onToggle?: () => void;
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

function PasswordField({
  label,
  value,
  onChange,
  minLength = 1,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  minLength?: number;
}) {
  return (
    <div>
      <label className="text-xs text-zinc-500 uppercase font-bold mb-1 block">
        {label}
      </label>
      <input
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
        minLength={minLength}
        autoComplete={label === "Senha atual" ? "current-password" : "new-password"}
        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-emerald-500"
      />
    </div>
  );
}

function getErrorDetail(error: unknown): string | null {
  if (
    error instanceof HttpError
    && error.status !== 401
    && error.responseBody
    && typeof error.responseBody === "object"
    && "detail" in error.responseBody
    && typeof error.responseBody.detail === "string"
  ) {
    return error.responseBody.detail;
  }
  return null;
}
