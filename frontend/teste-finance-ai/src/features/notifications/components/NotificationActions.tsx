"use client";

import Link from "next/link";
import { ExternalLink, Check } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { NotificationStatus, type Notification } from "../types";
import { useMarkNotificationRead } from "../hooks";

export type NotificationActionsProps = {
  notification: Notification;
  className?: string;
};

export function NotificationActions({
  notification,
  className,
}: NotificationActionsProps) {
  const markRead = useMarkNotificationRead();
  const isUnread = notification.status === NotificationStatus.Unread;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {notification.action_url ? (
        <Button asChild variant="outline" size="sm" aria-label="Abrir ação">
          <Link href={notification.action_url}>
            <ExternalLink size={16} />
            Abrir
          </Link>
        </Button>
      ) : null}

      {isUnread ? (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => markRead.mutate({ id: notification.id })}
          disabled={markRead.isPending}
          aria-label="Marcar como lida"
        >
          <Check size={16} />
          Marcar como lida
        </Button>
      ) : null}
    </div>
  );
}

