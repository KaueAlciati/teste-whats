"use client";

import { useToast } from "@/contexts/ToastContext";
import { CheckCircle, XCircle, Info, AlertCircle, X } from "lucide-react";

const typeStyles = {
  success: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
  error: "bg-red-500/10 border-red-500/30 text-red-400",
  warning: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  info: "bg-blue-500/10 border-blue-500/30 text-blue-400",
};

const typeIcons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertCircle,
  info: Info,
};

export function Toasts() {
  const { toasts, removeToast } = useToast();

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => {
        const Icon = typeIcons[toast.type];
        return (
          <div
            key={toast.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${typeStyles[toast.type]} backdrop-blur-sm animate-in slide-in-from-right fade-in duration-300`}
          >
            <Icon size={20} />
            <p className="text-sm font-medium">{toast.message}</p>
            <button
              onClick={() => removeToast(toast.id)}
              className="ml-2 hover:opacity-80 transition-opacity"
              aria-label="Fechar notificação"
            >
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
