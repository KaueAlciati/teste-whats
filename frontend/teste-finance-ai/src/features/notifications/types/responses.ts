import { type Notification } from "./notification";

export type ListNotificationsResponse = {
  items: Notification[];
  page: number;
  page_size: number;
  total: number;
};

export type MarkNotificationAsReadResponse = {
  ok: boolean;
};

export type MarkAllNotificationsAsReadResponse = {
  ok: boolean;
};
