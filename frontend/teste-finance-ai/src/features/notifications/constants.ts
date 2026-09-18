import {
  NotificationCategory,
  NotificationPriority,
  NotificationStatus,
} from "./types";

export const NOTIFICATIONS_DEFAULT_PAGE_SIZE = 20;

export const NOTIFICATION_STATUS_LABEL: Record<NotificationStatus, string> = {
  [NotificationStatus.Unread]: "Não lida",
  [NotificationStatus.Read]: "Lida",
};

export const NOTIFICATION_CATEGORY_LABEL: Record<NotificationCategory, string> = {
  [NotificationCategory.Financeiro]: "Financeiro",
  [NotificationCategory.Sistema]: "Sistema",
  [NotificationCategory.IA]: "IA",
  [NotificationCategory.Seguranca]: "Segurança",
  [NotificationCategory.Atualizacoes]: "Atualizações",
  [NotificationCategory.Lembretes]: "Lembretes",
};

export const NOTIFICATION_PRIORITY_LABEL: Record<NotificationPriority, string> = {
  [NotificationPriority.Low]: "Baixa",
  [NotificationPriority.Normal]: "Normal",
  [NotificationPriority.High]: "Alta",
  [NotificationPriority.Urgent]: "Urgente",
};
