"use client";

import { Bell, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { usePathname } from "next/navigation";
import { NotificationBadge, useNotificationsQuery } from "@/features/notifications";
import { NotificationStatus } from "@/features/notifications/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui";

const pageTitles: Record<string, { title: string; subtitle?: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Visão geral das suas finanças" },
  "/notifications": { title: "Notificações", subtitle: "Central de avisos e eventos" },
  "/transactions": { title: "Transações", subtitle: "Histórico financeiro completo" },
  "/planning": { title: "Planejamento", subtitle: "Metas e objetivos financeiros" },
  "/insights": { title: "Insights de IA", subtitle: "Análises inteligentes" },
  "/settings": { title: "Configurações", subtitle: "Personalize sua experiência" },
};

export function Navbar() {
  const { user } = useAuth();
  const pathname = usePathname();
  const unreadCountQuery = useNotificationsQuery(
    { status: NotificationStatus.Unread, page: 1, page_size: 1 },
    { toastOnError: false },
  );
  const unreadCount = unreadCountQuery.data?.total ?? 0;

  const page = pageTitles[pathname] || { title: "", subtitle: "" };

  // Centralizado em <LogoutConfirmDialog />, montado uma única vez em
  // AppLayout — este botão só avisa que o usuário quer sair, e deixa
  // a confirmação/execução do logout num só lugar do sistema.
  const requestLogout = () => {
    window.dispatchEvent(new Event("request-logout"));
  };

  const userInitials = user?.name
    ?.split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "U";

  return (
    <header
      className="h-14 md:h-16 border-b border-zinc-800/60 bg-zinc-950/70 backdrop-blur-md flex items-center justify-between px-4 sm:px-6 shrink-0 sticky top-0 z-30"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
    >
      <div className="flex items-center gap-3 md:gap-4 min-w-0">
        {/* Espaço reservado pro botão hambúrguer flutuante do Sidebar,
            que só existe abaixo de "lg" — esse spacer usava "md:hidden"
            antes, um breakpoint diferente do hambúrguer ("lg:hidden"),
            então em telas entre md e lg (tablets) o título ficava embaixo
            do botão. Agora os dois usam o mesmo breakpoint. */}
        <div className="w-11 lg:hidden shrink-0" />
        <div className="min-w-0">
          <h1 className="text-base md:text-lg font-bold tracking-tight truncate">
            {page.title}
          </h1>
          {page.subtitle && (
            <p className="text-xs text-zinc-500 truncate hidden sm:block">
              {page.subtitle}
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 md:gap-2">
        <Link
          href="/notifications"
          className="flex items-center justify-center p-2 hover:bg-zinc-800/70 rounded-xl transition-all duration-200 text-zinc-400 hover:text-zinc-200 relative active:scale-95 focus:outline-none focus:ring-1 focus:ring-zinc-700"
          aria-label="Notificações"
        >
          <Bell size={18} />
          <NotificationBadge
            count={unreadCount}
            className="absolute -top-1 -right-1 md:static md:ml-2 px-1.5 py-0.5 text-[10px]"
          />
        </Link>

        {/* Único lugar do sistema com o avatar/menu do usuário — antes
            existia também no rodapé do Sidebar (duplicado em desktop e
            no drawer mobile). Fica no header, visível em qualquer
            tamanho de tela, e pensado primeiro para o polegar: no
            celular é o canto mais fácil de alcançar com uma mão. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex items-center gap-2 p-1.5 hover:bg-zinc-800/70 rounded-xl transition-all duration-200 active:scale-95 focus:outline-none focus:ring-1 focus:ring-zinc-700 ml-1"
              aria-label="Menu do usuário"
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center text-xs font-bold text-white shadow-sm shadow-emerald-500/20 ring-1 ring-white/10 shrink-0">
                {userInitials}
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64 sm:w-72 rounded-2xl p-0 overflow-hidden">
            <div className="p-4 border-b border-zinc-800/60">
              <p className="text-sm font-semibold text-zinc-200 truncate tracking-tight">
                {user?.name}
              </p>
              <p className="text-xs text-zinc-500 truncate mt-0.5">
                {user?.email}
              </p>
            </div>
            <div className="p-2">
              <DropdownMenuItem asChild>
                <Link
                  href="/settings"
                  className="flex items-center gap-3 px-3 py-2.5 text-sm text-zinc-300 rounded-xl cursor-pointer"
                >
                  <Settings size={17} />
                  <span className="font-medium">Configurações</span>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={requestLogout}
                className="flex items-center gap-3 px-3 py-2.5 text-sm text-zinc-300 rounded-xl cursor-pointer hover:text-rose-400 group"
              >
                <LogOut size={17} className="group-hover:scale-110 transition-transform" />
                <span className="font-medium">Sair</span>
              </DropdownMenuItem>
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
