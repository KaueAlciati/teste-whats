"use client";

import { Badge } from "@/components/ui";
import { cn } from "@/lib/cn";

export type NotificationBadgeProps = {
  count: number;
  className?: string;
};

export function NotificationBadge({ count, className }: NotificationBadgeProps) {
  if (count <= 0) return null;

  return (
    <Badge
      className={cn("tabular-nums", className)}
      aria-label={`${count} notificações não lidas`}
    >
      {count}
    </Badge>
  );
}

