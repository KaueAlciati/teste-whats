import { NotificationCategory, NotificationPriority, NotificationStatus } from "./enums";

export type Notification = {
  id: number;
  title: string;
  description?: string | null;
  category: NotificationCategory;
  priority: NotificationPriority;
  status: NotificationStatus;
  created_at: string;
  read_at?: string | null;
  action_url?: string | null;
  metadata?: Record<string, unknown> | null;
};
