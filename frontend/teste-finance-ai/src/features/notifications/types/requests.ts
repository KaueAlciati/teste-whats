import { NotificationCategory, NotificationPriority, NotificationStatus } from "./enums";

export type ListNotificationsRequest = {
  page?: number;
  page_size?: number;
  q?: string;
  category?: NotificationCategory;
  priority?: NotificationPriority;
  status?: NotificationStatus;
  from?: string;
  to?: string;
};

export type MarkNotificationAsReadRequest = {
  id: number;
};

export type MarkAllNotificationsAsReadRequest = {
  q?: string;
  category?: NotificationCategory;
  priority?: NotificationPriority;
  from?: string;
  to?: string;
};
