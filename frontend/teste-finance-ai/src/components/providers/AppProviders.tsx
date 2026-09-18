"use client";

import { ReactNode, useEffect } from "react";
import { Toasts } from "@/components/Toast";
import { AuthProvider } from "@/contexts/AuthContext";
import { DataProvider } from "@/contexts/DataContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { checkBackendAvailability } from "@/lib/storage";

export function AppProviders({ children }: { children: ReactNode }) {
  useEffect(() => {
    checkBackendAvailability().catch(() => {
      // Fallback para modo local em caso de erro
    });
  }, []);

  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={200}>
        <QueryProvider>
          <AuthProvider>
            <ToastProvider>
              <DataProvider>
                {children}
                <Toasts />
              </DataProvider>
            </ToastProvider>
          </AuthProvider>
        </QueryProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
