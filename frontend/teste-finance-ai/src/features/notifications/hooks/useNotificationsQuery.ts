"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useToast } from "@/contexts/ToastContext";
import { notificationsService } from "../service";
import { notificationQueryKeys } from "../queryKeys";
import { type ListNotificationsRequest, type ListNotificationsResponse } from "../types";

export type UseNotificationsQueryOptions = {
  toastOnError?: boolean;
};

export function useNotificationsQuery(
  params: ListNotificationsRequest,
  options: UseNotificationsQueryOptions = {},
) {
  const { addToast } = useToast();
  const toastOnError = options.toastOnError ?? true;
  const hasNotifiedRef = useRef(false);

  const query = useQuery<ListNotificationsResponse, Error, ListNotificationsResponse>({
    queryKey: notificationQueryKeys.byFilters(params),
    queryFn: async () => notificationsService.list(params),
    placeholderData: keepPreviousData,
    retry: 1,
  });

  useEffect(() => {
    if (!toastOnError) return;
    if (!query.isError) return;
    if (hasNotifiedRef.current) return;

    addToast("error", "Erro ao carregar notificações.");
    hasNotifiedRef.current = true;
  }, [addToast, query.isError, toastOnError]);

  useEffect(() => {
    if (query.isSuccess) hasNotifiedRef.current = false;
  }, [query.isSuccess]);

  return query;
}
