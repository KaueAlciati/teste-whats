"use client";

import { useState } from "react";
import {
  LayoutDashboard,
  Wallet,
  Receipt,
  Settings,
  BrainCircuit,
  Menu,
  X,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const menuItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/dashboard" },
  { icon: Receipt, label: "Transações", href: "/transactions" },
  { icon: UploadCloud, label: "Importar extrato", href: "/transactions/import" },
  { icon: Wallet, label: "Planejamento", href: "/planning" },
  { icon: BrainCircuit, label: "Insights IA", href: "/insights" },
  { icon: Settings, label: "Configurações", href: "/settings" },
];

// Uma rota é "ativa" se for exatamente igual, ou se for uma sub-rota
// dela (ex: /transactions/42 também deve destacar "Transações") — mas
// só quando nenhum item do menu casar de forma mais específica (ex:
// /transactions/import deve destacar só "Importar extrato", não
// "Transações" também).
function isRouteActive(pathname: string, href: string, allHrefs: string[]) {
  const isMatch = pathname === href || pathname.startsWith(`${href}/`);
  if (!isMatch) return false;

  const hasMoreSpecificMatch = allHrefs.some(
    (other) =>
      other !== href &&
      other.startsWith(`${href}/`) &&
      (pathname === other || pathname.startsWith(`${other}/`)),
  );
  return !hasMoreSpecificMatch;
}

export function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const closeMenu = () => setIsOpen(false);

  return (
    <>
      {/* Botão hambúrguer — só existe em telas menores que "lg". O
          top usa env(safe-area-inset-top) pra não ficar embaixo do
          notch/relógio em iPhones com tela em "ilha dinâmica". */}
      <button
        onClick={() => setIsOpen(true)}
        aria-label="Abrir menu"
        className="fixed left-4 z-50 grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-zinc-800 bg-zinc-900 p-0 leading-none text-zinc-300 shadow-lg active:scale-95 transition-transform lg:hidden"
        style={{ top: "calc(1rem + env(safe-area-inset-top))" }}
      >
        <Menu size={20} className="block" />
      </button>

      {/* Fundo escurecido atrás do menu aberto no mobile */}
      {isOpen && (
        <div
          onClick={closeMenu}
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-72 sm:w-64 flex-col overflow-hidden border-r border-zinc-800 bg-zinc-950 transition-transform duration-200 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          lg:static lg:z-auto lg:translate-x-0`}
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <div className="flex items-center justify-between p-6">
          <h1 className="flex items-center gap-2 font-bold text-xl tracking-tight">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500 text-[13px] font-mono font-bold text-emerald-950">
              $
            </span>
            <span className="text-zinc-50">
              Finance<span className="text-emerald-500">.ai</span>
            </span>
          </h1>

          {/* Botão de fechar — só aparece dentro do drawer mobile */}
          <button
            onClick={closeMenu}
            aria-label="Fechar menu"
            className="flex h-9 w-9 items-center justify-center text-zinc-500 hover:text-zinc-300 lg:hidden"
          >
            <X size={20} />
          </button>
        </div>

        {/* Sem cartão de perfil/avatar aqui embaixo de propósito — ele
            existia duplicado (neste rodapé e no header, via Navbar) e
            agora vive só no header, pensando em quem usa o app no
            celular (ver Navbar.tsx). "Configurações" continua como
            item de navegação normal, e o padding inferior segue
            respeitando a "ilha" de gestos do iPhone. */}
        <nav
          className="flex-1 min-h-0 overflow-y-auto px-4 pt-1 space-y-1"
          style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
        >
          {menuItems.map((item) => {
            const isActive = isRouteActive(
              pathname,
              item.href,
              menuItems.map((m) => m.href),
            );

            return (
              <Link
                key={item.label}
                href={item.href}
                onClick={closeMenu}
                className={`relative flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
                }`}
              >
                {isActive && (
                  <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-emerald-500" />
                )}
                <item.icon size={20} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
