"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useToast } from "@/contexts/ToastContext";
import { notificationsService } from "../service";
import { notificationQueryKeys } from "../queryKeys";
import {
  NotificationStatus,
  type ListNotificationsRequest,
  type ListNotificationsResponse,
  type MarkAllNotificationsAsReadRequest,
} from "../types";

type MarkAllNotificationsReadContext = {
  previousQueries: Array<[QueryKey, ListNotificationsResponse | undefined]>;
};

function getListParamsFromKey(key: QueryKey): ListNotificationsRequest | undefined {
  if (!Array.isArray(key)) return undefined;
  if (key.length < 2) return undefined;
  if (key[0] !== "notifications") return undefined;
  if (key[1] !== "list") return undefined;
  const params = key[2];
  return (params ?? undefined) as ListNotificationsRequest | undefined;
}

function sameFilter(
  listParams: ListNotificationsRequest | undefined,
  filters: MarkAllNotificationsAsReadRequest,
) {
  return (
    (listParams?.q ?? undefined) === (filters.q ?? undefined) &&
    (listParams?.category ?? undefined) === (filters.category ?? undefined) &&
    (listParams?.priority ?? undefined) === (filters.priority ?? undefined) &&
    (listParams?.from ?? undefined) === (filters.from ?? undefined) &&
    (listParams?.to ?? undefined) === (filters.to ?? undefined)
  );
}

function markAllReadInList(
  data: ListNotificationsResponse | undefined,
  nowIso: string,
  listParams: ListNotificationsRequest | undefined,
): ListNotificationsResponse | undefined {
  if (!data) return data;

  if (listParams?.status === NotificationStatus.Unread) {
    return { ...data, items: [], total: 0 };
  }

  return {
    ...data,
    items: data.items.map((n) => ({
      ...n,
      status: NotificationStatus.Read,
      read_at: n.read_at ?? nowIso,
    })),
  };
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  return useMutation({
    mutationFn: async (filters: MarkAllNotificationsAsReadRequest) =>
      notificationsService.markAllAsRead(filters),
    onMutate: async (filters) => {
      await queryClient.cancelQueries({ queryKey: notificationQueryKeys.all });

      const previousQueries = queryClient.getQueriesData<ListNotificationsResponse>({
        queryKey: notificationQueryKeys.all,
      });

      const nowIso = new Date().toISOString();

      previousQueries.forEach(([key, data]) => {
        const params = getListParamsFromKey(key);
        if (!sameFilter(params, filters)) return;
        const next = markAllReadInList(data, nowIso, params);
        queryClient.setQueryData(key, next);
      });

      return { previousQueries } satisfies MarkAllNotificationsReadContext;
    },
    onError: (_err, _filters, context) => {
      context?.previousQueries.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });

      addToast("error", "Não foi possível marcar todas como lidas.");
    },
    onSuccess: () => {
      addToast("success", "Todas as notificações foram marcadas como lidas.");
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: notificationQueryKeys.all });
    },
  });
}

