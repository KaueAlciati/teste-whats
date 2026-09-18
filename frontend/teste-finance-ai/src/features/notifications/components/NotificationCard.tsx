"use client";

import { Bell, AlertTriangle } from "lucide-react";
import {
  Badge,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  NOTIFICATION_CATEGORY_LABEL,
  NOTIFICATION_PRIORITY_LABEL,
  NOTIFICATION_STATUS_LABEL,
} from "../constants";
import { NotificationPriority, NotificationStatus, type Notification } from "../types";
import { NotificationActions } from "./NotificationActions";

export type NotificationCardProps = {
  notification: Notification;
  className?: string;
};

function formatDateTime(value: string) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusVariant(status: NotificationStatus) {
  if (status === NotificationStatus.Unread) return "default";
  return "outline";
}

function priorityIcon(priority: NotificationPriority) {
  if (priority === NotificationPriority.Urgent) return <AlertTriangle size={14} />;
  return <Bell size={14} />;
}

export function NotificationCard({ notification, className }: NotificationCardProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden transition-colors",
        notification.status === NotificationStatus.Unread
          ? "border-primary/25 bg-primary/5"
          : undefined,
        className,
      )}
      aria-label={`Notificação: ${notification.title}`}
    >
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{NOTIFICATION_CATEGORY_LABEL[notification.category]}</Badge>
          <Badge variant="outline" className="gap-1">
            {priorityIcon(notification.priority)}
            {NOTIFICATION_PRIORITY_LABEL[notification.priority]}
          </Badge>
          <Badge variant={statusVariant(notification.status)}>
            {NOTIFICATION_STATUS_LABEL[notification.status]}
          </Badge>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <CardTitle className="text-base leading-snug">
              {notification.title}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {formatDateTime(notification.created_at)}
            </p>
          </div>

          {notification.status === NotificationStatus.Unread ? (
            <span
              className="mt-1 inline-flex h-2.5 w-2.5 shrink-0 rounded-full bg-primary shadow-sm shadow-primary/40"
              aria-label="Não lida"
            />
          ) : null}
        </div>
      </CardHeader>

      {notification.description ? (
        <CardContent className="pt-0">
          <p className="text-sm text-card-foreground/90 leading-relaxed">
            {notification.description}
          </p>
        </CardContent>
      ) : null}

      <CardFooter className="pt-0">
        <NotificationActions notification={notification} />
      </CardFooter>
    </Card>
  );
}

