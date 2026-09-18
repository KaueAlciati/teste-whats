"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { Skeleton } from "./Skeleton";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();

  // Importante: redirect() do next/navigation, quando chamado durante
  // a renderização de um Client Component, funciona bem no carregamento
  // inicial de uma rota sem sessão — mas não é confiável para reagir a
  // uma mudança de estado que acontece DEPOIS que a página já está
  // renderizada (como o logout, que muda `session` para null em tempo
  // de execução). Por isso o redirecionamento fica num efeito, com
  // router.push — o padrão recomendado para esse cenário no App Router.
  useEffect(() => {
    if (!loading && !session) {
      router.replace("/login");
    }
  }, [loading, session, router]);

  if (loading || !session) {
    return (
      <div className="flex-1 p-8 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Skeleton className="w-12 h-12 rounded-full" />
          <Skeleton className="w-32 h-4 rounded" />
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
