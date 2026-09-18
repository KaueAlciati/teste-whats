import { storageNotificationsService } from "@/lib/storage";
import {
  type ListNotificationsRequest,
  type ListNotificationsResponse,
  type MarkAllNotificationsAsReadRequest,
  type MarkAllNotificationsAsReadResponse,
  type MarkNotificationAsReadResponse,
} from "./types";

export const notificationsService = {
  list: async (
    params: ListNotificationsRequest,
  ): Promise<ListNotificationsResponse> => {
    return await storageNotificationsService.list(params);
  },

  markAsRead: async (id: number): Promise<MarkNotificationAsReadResponse> => {
    return await storageNotificationsService.markAsRead(id);
  },

  markAllAsRead: async (
    params: MarkAllNotificationsAsReadRequest,
  ): Promise<MarkAllNotificationsAsReadResponse> => {
    return await storageNotificationsService.markAllAsRead(params);
  },
};

