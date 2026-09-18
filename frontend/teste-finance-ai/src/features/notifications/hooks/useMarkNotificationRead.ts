"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useToast } from "@/contexts/ToastContext";
import { notificationsService } from "../service";
import { notificationQueryKeys } from "../queryKeys";
import {
  NotificationStatus,
  type ListNotificationsRequest,
  type ListNotificationsResponse,
} from "../types";

type MarkNotificationReadVariables = {
  id: number;
};

type MarkNotificationReadContext = {
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

function applyMarkAsRead(
  data: ListNotificationsResponse | undefined,
  notificationId: number,
  nowIso: string,
  listParams: ListNotificationsRequest | undefined,
): ListNotificationsResponse | undefined {
  if (!data) return data;

  const isUnreadList = listParams?.status === NotificationStatus.Unread;
  const existing = data.items.find((n) => n.id === notificationId);

  if (!existing) return data;

  if (isUnreadList) {
    return {
      ...data,
      items: data.items.filter((n) => n.id !== notificationId),
      total: Math.max(0, data.total - 1),
    };
  }

  return {
    ...data,
    items: data.items.map((n) =>
      n.id === notificationId
        ? { ...n, status: NotificationStatus.Read, read_at: nowIso }
        : n,
    ),
  };
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  return useMutation({
    mutationFn: async ({ id }: MarkNotificationReadVariables) =>
      notificationsService.markAsRead(id),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: notificationQueryKeys.all });

      const previousQueries = queryClient.getQueriesData<ListNotificationsResponse>({
        queryKey: notificationQueryKeys.all,
      });

      const nowIso = new Date().toISOString();

      previousQueries.forEach(([key, data]) => {
        const params = getListParamsFromKey(key);
        const next = applyMarkAsRead(data, id, nowIso, params);
        queryClient.setQueryData(key, next);
      });

      return { previousQueries } satisfies MarkNotificationReadContext;
    },
    onError: (_err, _variables, context) => {
      context?.previousQueries.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });

      addToast("error", "Não foi possível marcar como lida.");
    },
    onSuccess: () => {
      addToast("success", "Notificação marcada como lida.");
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: notificationQueryKeys.all });
    },
  });
}

