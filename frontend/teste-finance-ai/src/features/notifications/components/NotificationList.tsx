"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { type Notification } from "../types";
import { NotificationCard } from "./NotificationCard";

type NotificationGroup = {
  key: string;
  label: string;
  items: Notification[];
};

export type NotificationListProps = {
  items: Notification[];
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (next: number) => void;
  className?: string;
};

function getDateKey(date: Date) {
  const year = String(date.getFullYear()).padStart(4, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatGroupLabel(dateKey: string) {
  const [y, m, d] = dateKey.split("-").map((part) => Number(part));
  const date = new Date(y, m - 1, d);
  const todayKey = getDateKey(new Date());

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = getDateKey(yesterday);

  if (dateKey === todayKey) return "Hoje";
  if (dateKey === yesterdayKey) return "Ontem";

  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}

export function NotificationList({
  items,
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: NotificationListProps) {
  const groups = useMemo<NotificationGroup[]>(() => {
    const map = new Map<string, Notification[]>();

    items.forEach((n) => {
      const key = getDateKey(new Date(n.created_at));
      const list = map.get(key) ?? [];
      list.push(n);
      map.set(key, list);
    });

    return Array.from(map.entries())
      .sort(([a], [b]) => (a > b ? -1 : 1))
      .map(([key, groupItems]) => ({
        key,
        label: formatGroupLabel(key),
        items: groupItems.sort((a, b) => (a.created_at > b.created_at ? -1 : 1)),
      }));
  }, [items]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className={cn("space-y-6", className)} aria-label="Lista de notificações">
      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.key} className="space-y-3" aria-label={group.label}>
            <h2 className="text-sm font-semibold text-muted-foreground">
              {group.label}
            </h2>
            <ul className="space-y-3">
              {group.items.map((notification) => (
                <li key={notification.id}>
                  <NotificationCard notification={notification} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="flex items-center justify-between gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={!canPrev}
          aria-label="Página anterior"
        >
          Anterior
        </Button>

        <span className="text-xs text-muted-foreground tabular-nums">
          Página {page} de {totalPages}
        </span>

        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={!canNext}
          aria-label="Próxima página"
        >
          Próxima
        </Button>
      </div>
    </div>
  );
}

