"use client";

import { useState, FormEvent } from "react";
import { storage } from "@/lib/storage";
import { useToast } from "@/contexts/ToastContext";
import Link from "next/link";
import { Mail, ArrowLeft, CheckCircle2 } from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const { addToast } = useToast();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await storage.forgotPassword(email);
      setSent(true);
      addToast("success", "Link de recuperação enviado. Confira seu e-mail.");
    } catch {
      addToast("error", "Erro ao enviar e-mail. Tente novamente.");
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 sm:p-6">
        <div className="w-full max-w-md">
          <div className="text-center mb-6 sm:mb-8">
            <Link href="/" className="inline-block">
              <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-emerald-500 mx-auto mb-4 shadow-lg shadow-emerald-500/20 ring-1 ring-white/10 flex items-center justify-center">
                <span className="text-black font-bold text-lg sm:text-xl">$</span>
              </div>
            </Link>
            <h1 className="text-2xl sm:text-3xl font-bold text-emerald-500 mb-2 tracking-tight">
              Finance.AI
            </h1>
          </div>

          <div className="bg-zinc-900/60 backdrop-blur-sm border border-zinc-800/70 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-2xl shadow-black/30 text-center">
            <div className="w-16 h-16 bg-emerald-500/10 rounded-2xl flex items-center justify-center mx-auto mb-5 ring-1 ring-emerald-500/20">
              <CheckCircle2 className="w-9 h-9 text-emerald-500" strokeWidth={2} />
            </div>
            <h2 className="text-xl sm:text-2xl font-semibold mb-2 tracking-tight">
              Verifique seu e-mail
            </h2>
            <p className="text-zinc-400 mb-6 text-sm sm:text-base leading-relaxed">
              Enviamos um link de recuperação para{" "}
              <span className="text-zinc-200 font-medium">{email}</span>
            </p>
            <Link
              href="/login"
              className="inline-flex items-center justify-center gap-2 w-full px-6 py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-zinc-950 shadow-lg shadow-emerald-500/10 hover:shadow-emerald-500/20"
            >
              <ArrowLeft size={18} />
              Voltar para login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-6 sm:mb-8">
          <Link href="/" className="inline-block">
            <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-emerald-500 mx-auto mb-4 shadow-lg shadow-emerald-500/20 ring-1 ring-white/10 flex items-center justify-center">
              <span className="text-black font-bold text-lg sm:text-xl">$</span>
            </div>
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold text-emerald-500 mb-2 tracking-tight">
            Finance.AI
          </h1>
          <p className="text-zinc-400 text-sm sm:text-base">
            Recupere o acesso à sua conta
          </p>
        </div>

        <div className="bg-zinc-900/60 backdrop-blur-sm border border-zinc-800/70 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-2xl shadow-black/30">
          <h2 className="text-xl sm:text-2xl font-semibold mb-2 tracking-tight">
            Esqueceu sua senha?
          </h2>
          <p className="text-zinc-400 mb-6 text-sm sm:text-base">
            Informe seu e-mail e enviaremos um link para recuperá-la.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
            <div className="space-y-2">
              <label
                htmlFor="email"
                className="block text-[11px] uppercase tracking-wider font-semibold text-zinc-400 ml-1"
              >
                E-mail
              </label>
              <div className="relative group">
                <Mail
                  size={18}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-emerald-500 transition-colors"
                />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-zinc-950/60 border border-zinc-700/70 rounded-xl pl-11 pr-3.5 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-zinc-900/80 transition-all"
                  placeholder="seu@email.com"
                  required
                  minLength={5}
                  maxLength={120}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-zinc-950 shadow-lg shadow-emerald-500/10 hover:shadow-emerald-500/20 tracking-wide"
            >
              {loading ? "Enviando..." : "Enviar link de recuperação"}
            </button>
          </form>

          <div className="mt-6 sm:mt-7">
            <p className="text-center text-zinc-400 text-sm">
              Lembrou sua senha?{" "}
              <Link
                href="/login"
                className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors"
              >
                Voltar para login
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
