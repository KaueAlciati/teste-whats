"use client";

import { useState, useEffect, FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Mail, Lock } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login, session, loading: authLoading } = useAuth();
  const { addToast } = useToast();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && session) {
      router.replace("/dashboard");
    }
  }, [authLoading, session, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await login(email, password);
      addToast("success", "Login realizado com sucesso!");
      router.push("/dashboard");
    } catch {
      addToast("error", "Erro ao fazer login. Verifique suas credenciais.");
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || session) return null;

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
            Gerencie suas finanças com inteligência artificial
          </p>
        </div>

        <div className="bg-zinc-900/50 backdrop-blur-sm border border-zinc-800/80 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-2xl shadow-black/30">
          <div className="mb-6 sm:mb-7">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Entrar na sua conta
            </h2>
            <p className="text-zinc-500 text-xs sm:text-sm mt-1.5">
              Informe suas credenciais para continuar
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
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
                  autoComplete="current-password"
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

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] hover:shadow-lg hover:shadow-emerald-500/20 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:ring-offset-2 focus:ring-offset-zinc-900 mt-1 text-sm tracking-wide"
            >
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>

          <div className="mt-6 sm:mt-7 space-y-5 sm:space-y-6">
            <Link
              href="/forgot-password"
              className="block text-center text-sm text-emerald-400 hover:text-emerald-300 font-medium transition-colors"
            >
              Esqueceu sua senha?
            </Link>

            <div className="flex items-center gap-3 sm:gap-4">
              <div className="flex-1 h-px bg-zinc-800" />
              <span className="text-zinc-600 text-xs font-medium">ou</span>
              <div className="flex-1 h-px bg-zinc-800" />
            </div>

            <p className="text-center text-zinc-400 text-sm">
              Não tem uma conta?{" "}
              <Link
                href="/register"
                className="text-emerald-400 hover:text-emerald-300 font-semibold transition-colors"
              >
                Criar conta
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
