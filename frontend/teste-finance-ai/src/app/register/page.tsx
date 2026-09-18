"use client";

import { useState, useEffect, FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import { storage } from "@/lib/storage";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Mail, Lock, User, Check, Loader2 } from "lucide-react";

type SetupStep = "account" | "profile" | "insights" | "done";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [setupStep, setSetupStep] = useState<SetupStep | null>(null);
  const { register, session, loading: authLoading } = useAuth();
  const { addToast } = useToast();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && session) {
      router.replace("/dashboard");
    }
  }, [authLoading, session, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    if (password !== confirmPassword) {
      addToast("error", "As senhas não coincidem.");
      return;
    }

    if (password.length < 8) {
      addToast("error", "A senha deve ter pelo menos 8 caracteres.");
      return;
    }

    setLoading(true);
    setSetupStep("account");

    try {
      await register(name, email, password);
      setSetupStep("profile");

      // Não é só decoração: aqui a tela já busca de verdade o resumo e
      // os insights que o Dashboard vai mostrar em seguida — pra quando
      // o usuário chegar lá, na maioria das vezes os dados já estejam
      // prontos, em vez de mostrar outro carregamento na sequência.
      setSetupStep("insights");
      await Promise.all([
        storage.getSummary().catch(() => null),
        storage.getInsights().catch(() => null),
      ]);

      setSetupStep("done");
      addToast("success", "Conta criada com sucesso!");
      router.push("/dashboard");
    } catch {
      addToast("error", "Erro ao criar conta. Tente novamente.");
      setSetupStep(null);
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || session) return null;

  if (setupStep) {
    return <PostRegisterSetup step={setupStep} />;
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-7 sm:mb-8">
          <Link href="/" className="inline-block">
            <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-emerald-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/20 ring-1 ring-white/10">
              <span className="text-black font-bold text-lg sm:text-xl">
                $
              </span>
            </div>
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold text-emerald-500 mb-2 tracking-tight">
            Finance.AI
          </h1>
          <p className="text-zinc-400 text-sm sm:text-base">
            Crie sua conta e comece a gerenciar suas finanças
          </p>
        </div>

        <div className="bg-zinc-900/50 backdrop-blur-sm border border-zinc-800/80 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-2xl shadow-black/30">
          <div className="mb-6 sm:mb-7">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Criar conta
            </h2>
            <p className="text-zinc-500 text-xs sm:text-sm mt-1.5">
              Preencha os campos abaixo para começar
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
            <div>
              <label
                htmlFor="name"
                className="block text-xs font-semibold text-zinc-300 mb-1.5 tracking-wide"
              >
                Nome completo
              </label>
              <div className="relative group">
                <User
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors shrink-0"
                  size={17}
                />
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-4 py-2.5 pl-11 bg-zinc-800/60 border border-zinc-700/70 rounded-xl text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-zinc-800 transition-all duration-200 placeholder:text-zinc-600 text-sm"
                  placeholder="Seu nome"
                  required
                  minLength={2}
                  maxLength={80}
                  autoComplete="name"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="email"
                className="block text-xs font-semibold text-zinc-300 mb-1.5 tracking-wide"
              >
                E-mail
              </label>
              <div className="relative group">
                <Mail
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors shrink-0"
                  size={17}
                />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2.5 pl-11 bg-zinc-800/60 border border-zinc-700/70 rounded-xl text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-zinc-800 transition-all duration-200 placeholder:text-zinc-600 text-sm"
                  placeholder="seu@email.com"
                  required
                  minLength={5}
                  maxLength={120}
                  autoComplete="email"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-semibold text-zinc-300 mb-1.5 tracking-wide"
              >
                Senha
              </label>
              <div className="relative group">
                <Lock
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors shrink-0"
                  size={17}
                />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 pl-11 pr-12 bg-zinc-800/60 border border-zinc-700/70 rounded-xl text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-zinc-800 transition-all duration-200 placeholder:text-zinc-600 text-sm"
                  placeholder="••••••••"
                  required
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors p-1 rounded-md hover:bg-zinc-700/50 focus:outline-none focus:ring-1 focus:ring-zinc-600"
                  aria-label={
                    showPassword ? "Ocultar senha" : "Mostrar senha"
                  }
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-xs font-semibold text-zinc-300 mb-1.5 tracking-wide"
              >
                Confirmar senha
              </label>
              <div className="relative group">
                <Lock
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors shrink-0"
                  size={17}
                />
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-2.5 pl-11 pr-12 bg-zinc-800/60 border border-zinc-700/70 rounded-xl text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-zinc-800 transition-all duration-200 placeholder:text-zinc-600 text-sm"
                  placeholder="••••••••"
                  required
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors p-1 rounded-md hover:bg-zinc-700/50 focus:outline-none focus:ring-1 focus:ring-zinc-600"
                  aria-label={
                    showConfirmPassword ? "Ocultar senha" : "Mostrar senha"
                  }
                >
                  {showConfirmPassword ? (
                    <EyeOff size={16} />
                  ) : (
                    <Eye size={16} />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] hover:shadow-lg hover:shadow-emerald-500/20 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:ring-offset-2 focus:ring-offset-zinc-900 mt-1 text-sm tracking-wide"
            >
              {loading ? "Criando..." : "Criar conta"}
            </button>
          </form>

          <div className="mt-6 sm:mt-7">
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="flex-1 h-px bg-zinc-800" />
              <span className="text-zinc-600 text-xs font-medium">ou</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            <p className="text-center text-zinc-400 text-sm mt-4 sm:mt-5">
              Já tem uma conta?{" "}
              <Link
                href="/login"
                className="text-emerald-400 hover:text-emerald-300 font-semibold transition-colors"
              >
                Entrar
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

const SETUP_STEPS: { key: SetupStep; label: string }[] = [
  { key: "account", label: "Conta criada" },
  { key: "profile", label: "Perfil configurado" },
  { key: "insights", label: "Preparando suas análises" },
];

/**
 * Tela exibida entre o cadastro e o Dashboard. Cada item reflete um
 * passo que realmente aconteceu (ou está acontecendo) — "Preparando
 * suas análises" corresponde à busca real do resumo e dos insights
 * que o Dashboard vai exibir em seguida, não é só uma animação.
 */
function PostRegisterSetup({ step }: { step: SetupStep }) {
  const currentIndex = SETUP_STEPS.findIndex((s) => s.key === step);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-sm text-center space-y-8">
        <div>
          <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-emerald-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/20 ring-1 ring-white/10">
            <span className="text-black font-bold text-lg sm:text-xl">$</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-emerald-500 tracking-tight">
            Finance.AI
          </h1>
          <p className="text-zinc-400 text-sm mt-1">Preparando seu espaço...</p>
        </div>

        <div className="space-y-3 text-left bg-zinc-900/50 border border-zinc-800/80 rounded-2xl p-5">
          {SETUP_STEPS.map((s, idx) => {
            const isDone = idx < currentIndex || step === "done";
            const isActive = idx === currentIndex && step !== "done";
            return (
              <div key={s.key} className="flex items-center gap-3">
                <span
                  className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
                    isDone
                      ? "bg-emerald-500 text-black"
                      : isActive
                        ? "border-2 border-emerald-500"
                        : "border-2 border-zinc-700"
                  }`}
                >
                  {isDone && <Check size={12} strokeWidth={3} />}
                  {isActive && <Loader2 size={12} className="animate-spin text-emerald-500" />}
                </span>
                <span
                  className={`text-sm ${
                    isDone ? "text-zinc-300" : isActive ? "text-zinc-200 font-medium" : "text-zinc-500"
                  }`}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
