"use client";

import { BellOff } from "lucide-react";
import { Button, EmptyState } from "@/components/ui";

export type NotificationEmptyStateProps = {
  hasActiveFilters: boolean;
  onClearFilters: () => void;
};

export function NotificationEmptyState({
  hasActiveFilters,
  onClearFilters,
}: NotificationEmptyStateProps) {
  return (
    <EmptyState
      icon={<BellOff size={18} />}
      title="Nenhuma notificação encontrada"
      description={
        hasActiveFilters
          ? "Tente ajustar sua busca ou remover filtros para ver mais resultados."
          : "Quando algo importante acontecer, suas notificações aparecem aqui."
      }
      action={
        hasActiveFilters ? (
          <Button variant="outline" onClick={onClearFilters} aria-label="Limpar filtros">
            Limpar filtros
          </Button>
        ) : null
      }
    />
  );
}

