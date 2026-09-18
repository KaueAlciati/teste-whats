"use client";

import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { Button, EmptyState } from "@/components/ui";
import {
  NOTIFICATIONS_DEFAULT_PAGE_SIZE,
  NotificationFilters,
  NotificationHeader,
  NotificationEmptyState,
  NotificationList,
  NotificationSearch,
  NotificationSkeleton,
  useNotificationsQuery,
} from "@/features/notifications";
import {
  NotificationStatus,
  type ListNotificationsRequest,
  type NotificationCategory,
  type NotificationPriority,
} from "@/features/notifications/types";

export default function NotificationsPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<NotificationCategory | undefined>(undefined);
  const [priority, setPriority] = useState<NotificationPriority | undefined>(undefined);
  const [status, setStatus] = useState<NotificationStatus | undefined>(undefined);
  const [from, setFrom] = useState<string | undefined>(undefined);
  const [to, setTo] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);

  const params = useMemo<ListNotificationsRequest>(() => {
    return {
      q: q.trim() ? q.trim() : undefined,
      category,
      priority,
      status,
      from,
      to,
      page,
      page_size: NOTIFICATIONS_DEFAULT_PAGE_SIZE,
    };
  }, [category, from, page, priority, q, status, to]);

  const notificationsQuery = useNotificationsQuery(params);

  const unreadCountQuery = useNotificationsQuery(
    { status: NotificationStatus.Unread, page: 1, page_size: 1 },
    { toastOnError: false },
  );

  const unreadCount = unreadCountQuery.data?.total ?? 0;

  const hasActiveFilters = Boolean(
    q.trim() || category || priority || status || from || to,
  );

  const clearFilters = () => {
    setQ("");
    setCategory(undefined);
    setPriority(undefined);
    setStatus(undefined);
    setFrom(undefined);
    setTo(undefined);
    setPage(1);
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <NotificationHeader
          unreadCount={unreadCount}
          markAllFilters={{
            q: q.trim() ? q.trim() : undefined,
            category,
            priority,
            from,
            to,
          }}
        />

        <div className="grid grid-cols-1 gap-3">
          <NotificationSearch
            value={q}
            onChange={(next) => {
              setQ(next);
              setPage(1);
            }}
          />

          <NotificationFilters
            category={category}
            priority={priority}
            status={status}
            from={from}
            to={to}
            onChange={(next) => {
              setCategory(next.category);
              setPriority(next.priority);
              setStatus(next.status);
              setFrom(next.from);
              setTo(next.to);
              setPage(1);
            }}
            onClear={clearFilters}
          />
        </div>

        {notificationsQuery.isLoading ? (
          <NotificationSkeleton />
        ) : notificationsQuery.isError ? (
          <EmptyState
            icon={<AlertTriangle size={18} />}
            title="Não foi possível carregar as notificações"
            description="Verifique sua conexão e tente novamente."
            action={
              <Button onClick={() => notificationsQuery.refetch()} aria-label="Tentar novamente">
                Tentar novamente
              </Button>
            }
          />
        ) : !notificationsQuery.data ? (
          <NotificationSkeleton />
        ) : notificationsQuery.data.items.length === 0 ? (
          <NotificationEmptyState
            hasActiveFilters={hasActiveFilters}
            onClearFilters={clearFilters}
          />
        ) : (
          <NotificationList
            items={notificationsQuery.data.items}
            page={notificationsQuery.data.page}
            pageSize={notificationsQuery.data.page_size}
            total={notificationsQuery.data.total}
            onPageChange={setPage}
          />
        )}
      </div>
    </AppLayout>
  );
}
