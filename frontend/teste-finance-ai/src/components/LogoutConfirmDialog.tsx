"use client";

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";

/**
 * Fica montado uma única vez em AppLayout. Qualquer botão "Sair" do
 * sistema (Sidebar, menu do usuário no mobile) dispara o evento
 * "request-logout" em vez de chamar logout() direto — assim o
 * comportamento (e a confirmação) fica centralizado em um só lugar,
 * não duplicado em cada botão.
 */
export function LogoutConfirmDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const { logout } = useAuth();
  const { addToast } = useToast();
  const router = useRouter();

  useEffect(() => {
    function handleRequest() {
      setOpen(true);
    }
    window.addEventListener("request-logout", handleRequest);
    return () => window.removeEventListener("request-logout", handleRequest);
  }, []);

  async function handleConfirm() {
    setLoading(true);
    try {
      await logout();
      addToast("success", "Você saiu da sua conta.");
      router.push("/login");
    } catch {
      addToast("error", "Não foi possível sair agora. Tente novamente.");
    } finally {
      setLoading(false);
      setOpen(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <div className="w-10 h-10 rounded-full bg-rose-500/10 flex items-center justify-center mb-2">
            <LogOut size={18} className="text-rose-400" />
          </div>
          <DialogTitle>Sair da sua conta?</DialogTitle>
          <DialogDescription>
            Você precisará entrar novamente com seu e-mail e senha para acessar o Finance.AI.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button
            onClick={() => setOpen(false)}
            className="px-4 py-2 rounded-lg text-sm font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-rose-600 hover:bg-rose-500 text-white transition-colors disabled:opacity-50"
          >
            {loading ? "Saindo..." : "Sair"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
