"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, Eye, EyeOff, Lock } from "lucide-react";
import { useToast } from "@/contexts/ToastContext";
import { storage } from "@/lib/storage";


export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}


function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const [token] = useState(() => searchParams.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    if (token && typeof window !== "undefined") {
      window.history.replaceState(
        window.history.state,
        "",
        "/reset-password",
      );
    }
  }, [token]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      addToast("error", "Link de recuperação inválido ou incompleto.");
      return;
    }
    if (password !== confirmation) {
      addToast("error", "A confirmação da nova senha não confere.");
      return;
    }

    setLoading(true);
    try {
      await storage.resetPassword({
        token,
        new_password: password,
        confirm_new_password: confirmation,
      });
      setCompleted(true);
      addToast("success", "Senha redefinida com sucesso.");
    } catch {
      addToast("error", "Este link é inválido ou expirou. Solicite um novo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-6 sm:mb-8">
          <Link href="/" className="inline-block">
            <Image
              src="/logo-fincontrol.png"
              alt="FinControl AI"
              width={160}
              height={96}
              className="h-24 w-40 object-contain mx-auto mb-4"
            />
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold text-emerald-500 mb-2 tracking-tight">
            FinControl AI
          </h1>
        </div>

        <div className="bg-zinc-900/60 backdrop-blur-sm border border-zinc-800/70 rounded-2xl sm:rounded-3xl p-6 sm:p-8 shadow-2xl shadow-black/30">
          {completed ? (
            <div className="text-center">
              <div className="w-16 h-16 bg-emerald-500/10 rounded-2xl flex items-center justify-center mx-auto mb-5 ring-1 ring-emerald-500/20">
                <CheckCircle2 className="w-9 h-9 text-emerald-500" />
              </div>
              <h2 className="text-xl sm:text-2xl font-semibold mb-2">
                Senha redefinida
              </h2>
              <p className="text-zinc-400 mb-6 text-sm sm:text-base">
                Sua nova senha já está ativa. Entre novamente para continuar.
              </p>
              <Link
                href="/login"
                className="inline-flex items-center justify-center gap-2 w-full px-6 py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all"
              >
                Ir para o login
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-xl sm:text-2xl font-semibold mb-2 tracking-tight">
                Definir nova senha
              </h2>
              <p className="text-zinc-400 mb-6 text-sm sm:text-base">
                Escolha uma senha segura com pelo menos 8 caracteres.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
                <PasswordInput
                  id="new-password"
                  label="Nova senha"
                  value={password}
                  onChange={setPassword}
                  visible={showPassword}
                  onToggle={() => setShowPassword((current) => !current)}
                />
                <PasswordInput
                  id="confirm-password"
                  label="Confirmar nova senha"
                  value={confirmation}
                  onChange={setConfirmation}
                  visible={showConfirmation}
                  onToggle={() => setShowConfirmation((current) => !current)}
                />
                <button
                  type="submit"
                  disabled={loading || !token}
                  className="w-full py-2.5 sm:py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? "Salvando..." : "Salvar nova senha"}
                </button>
              </form>

              {!token && (
                <p className="mt-4 text-sm text-amber-400 text-center">
                  Link inválido ou incompleto. Solicite uma nova recuperação.
                </p>
              )}
              <Link
                href="/login"
                className="mt-6 inline-flex items-center justify-center gap-2 w-full text-sm text-emerald-400 hover:text-emerald-300"
              >
                <ArrowLeft size={17} />
                Voltar para login
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}


function PasswordInput({
  id,
  label,
  value,
  onChange,
  visible,
  onToggle,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  visible: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={id}
        className="block text-[11px] uppercase tracking-wider font-semibold text-zinc-400 ml-1"
      >
        {label}
      </label>
      <div className="relative group">
        <Lock
          size={18}
          className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500"
        />
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full bg-zinc-950/60 border border-zinc-700/70 rounded-xl pl-11 pr-12 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-emerald-500"
          required
          minLength={8}
          maxLength={128}
        />
        <button
          type="button"
          onClick={onToggle}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 p-1"
          aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </div>
  );
}
