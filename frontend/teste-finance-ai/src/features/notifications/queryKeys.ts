import { createFeatureQueryKeys } from "@/lib/query-keys/core";
import { NotificationStatus, type ListNotificationsRequest } from "./types";

const keys = createFeatureQueryKeys("notifications");

export const notificationQueryKeys = {
  ...keys,
  list: (params?: ListNotificationsRequest) => keys.list(params),
  byFilters: (params?: ListNotificationsRequest) => keys.list(params),
  unread: (params?: Omit<ListNotificationsRequest, "status">) =>
    keys.list({ ...params, status: NotificationStatus.Unread }),
  unreadCount: (params?: Omit<ListNotificationsRequest, "status" | "page_size">) =>
    keys.list({ ...params, status: NotificationStatus.Unread, page_size: 1 }),
};
