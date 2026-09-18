"use client";

import { useCallback } from "react";
import { HttpError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/contexts/ToastContext";

/**
 * Centraliza o que fazer quando uma chamada à API falha, para não
 * repetir essa lógica em cada tela (Extrato, Planejamento, Insights,
 * Dashboard...).
 *
 * - 401 (sessão inválida/expirada de verdade) → desloga e avisa,
 *   deixando o ProtectedRoute redirecionar para o login. Antes,
 *   um 401 virava silenciosamente uma lista vazia, como se o
 *   usuário não tivesse nenhum dado — o que é enganoso.
 * - Qualquer outro erro → mostra um toast, sem quebrar a tela.
 */
export function useHandleFetchError() {
  const { logout } = useAuth();
  const { addToast } = useToast();

  return useCallback(
    async (err: unknown, context: string) => {
      if (err instanceof HttpError && err.status === 401) {
        addToast("warning", "Sua sessão expirou. Faça login novamente.");
        await logout();
        return;
      }
      console.error(context, err);
      addToast("error", "Não foi possível carregar seus dados agora. Tente novamente.");
    },
    [logout, addToast],
  );
}
