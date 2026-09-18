"use client";

import { Bell } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useMarkAllNotificationsRead } from "../hooks";
import { type MarkAllNotificationsAsReadRequest } from "../types";
import { NotificationBadge } from "./NotificationBadge";

export type NotificationHeaderProps = {
  unreadCount: number;
  markAllFilters: MarkAllNotificationsAsReadRequest;
  className?: string;
};

export function NotificationHeader({
  unreadCount,
  markAllFilters,
  className,
}: NotificationHeaderProps) {
  const markAll = useMarkAllNotificationsRead();

  const canMarkAll = unreadCount > 0;

  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between", className)}>
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-muted text-foreground">
          <Bell size={18} />
        </div>
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold tracking-tight truncate">
            Notificações
          </h1>
          <div className="mt-1 flex items-center gap-2">
            <NotificationBadge count={unreadCount} />
            <span className="text-xs text-muted-foreground">
              não lidas
            </span>
          </div>
        </div>
      </div>

      <Button
        variant="outline"
        onClick={() => markAll.mutate(markAllFilters)}
        disabled={!canMarkAll || markAll.isPending}
        aria-label="Marcar todas como lidas"
      >
        Marcar todas como lidas
      </Button>
    </div>
  );
}

