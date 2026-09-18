"use client";

import { useEffect, useState } from "react";
import {
  api,
  API_URL,
  isBackendUnavailableError,
  type AuthSession,
  type ChartDataPoint,
  type DashboardSummary,
  type Goal,
  type ImportBatchSummary,
  type ImportConfirmResponse,
  type ImportConfirmRow,
  type ImportPreviewResponse,
  type InsightData,
  type Transaction,
  type UserProfile,
  type UserSettings,
} from "./api";
import {
  localStorageApi,
  localStorageNotificationsService,
} from "./localStorage";
import type {
  ListNotificationsRequest,
  ListNotificationsResponse,
  MarkAllNotificationsAsReadRequest,
  MarkAllNotificationsAsReadResponse,
  MarkNotificationAsReadResponse,
} from "@/features/notifications/types";

export type StorageMode = "api" | "local";

type StorageModeListener = (mode: StorageMode) => void;

let currentMode: StorageMode | null = null;
let availabilityCheckPromise: Promise<StorageMode> | null = null;
const listeners: Set<StorageModeListener> = new Set();

function setMode(mode: StorageMode): void {
  if (currentMode === mode) return;
  currentMode = mode;
  listeners.forEach((fn) => {
    try {
      fn(mode);
    } catch {
      // ignore
    }
  });
}

export function subscribeStorageMode(listener: StorageModeListener): () => void {
  listeners.add(listener);
  if (currentMode !== null) {
    try {
      listener(currentMode);
    } catch {
      // ignore
    }
  }
  return () => {
    listeners.delete(listener);
  };
}

export function getStorageMode(): StorageMode | null {
  return currentMode;
}

function buildHealthUrl(): string {
  const url = API_URL.replace(/\/api\/?$/, "");
  return url === "" ? "/" : `${url}/`;
}

async function lightweightHealthCheck(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 3000);
  try {
    const healthUrl = buildHealthUrl();
    const res = await fetch(healthUrl, {
      method: "GET",
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timeoutId);
    return res.ok;
  } catch {
    clearTimeout(timeoutId);
    return false;
  }
}

export async function checkBackendAvailability(force = false): Promise<StorageMode> {
  if (typeof window === "undefined") return "local";

  if (currentMode !== null && !force) return currentMode;

  if (availabilityCheckPromise !== null && !force) {
    return availabilityCheckPromise;
  }

  availabilityCheckPromise = (async () => {
    try {
      const healthy = await lightweightHealthCheck();
      const mode: StorageMode = healthy ? "api" : "local";
      setMode(mode);
      return mode;
    } catch {
      setMode("local");
      return "local" as StorageMode;
    } finally {
      availabilityCheckPromise = null;
    }
  })();

  return availabilityCheckPromise;
}

async function resolveModeForWrite(): Promise<StorageMode> {
  if (currentMode !== null) return currentMode;
  return checkBackendAvailability();
}

async function fallbackRead<T>(
  apiFn: () => Promise<T>,
  localFn: () => Promise<T>,
): Promise<T> {
  if (typeof window === "undefined") {
    return apiFn();
  }

  const cached = getStorageMode();

  if (cached === "local") {
    return localFn();
  }

  try {
    const result = await apiFn();
    if (cached === null) setMode("api");
    return result;
  } catch (err) {
    if (isBackendUnavailableError(err)) {
      setMode("local");
      return localFn();
    }
    throw err;
  }
}

async function resolveWrite<T>(
  apiFn: () => Promise<T>,
  localFn: () => Promise<T>,
): Promise<T> {
  const mode = await resolveModeForWrite();
  if (mode === "local") return localFn();
  try {
    return await apiFn();
  } catch (err) {
    if (isBackendUnavailableError(err)) {
      setMode("local");
      return localFn();
    }
    throw err;
  }
}

export const storage = {
  request: async <T,>(
    path: string,
    options: RequestInit = {},
    params?: Record<string, unknown>,
  ): Promise<T> => {
    const cached = getStorageMode();
    if (cached === "local") {
      return localStorageApi.request<T>(path, options, params);
    }
    try {
      return await api.request<T>(path, options, params);
    } catch (err) {
      if (isBackendUnavailableError(err)) {
        setMode("local");
        return localStorageApi.request<T>(path, options, params);
      }
      throw err;
    }
  },

  resetDatabase: async () => {
    const mode = await resolveModeForWrite();
    if (mode === "local") return localStorageApi.resetDatabase();
    try {
      return await api.resetDatabase();
    } catch (err) {
      if (isBackendUnavailableError(err)) {
        setMode("local");
        return localStorageApi.resetDatabase();
      }
      throw err;
    }
  },

  // --- Auth ---
  login: async (data: { email: string; password: string }): Promise<AuthSession> =>
    resolveWrite(
      () => api.login(data),
      () => localStorageApi.login(data),
    ),

  register: async (data: {
    name: string;
    email: string;
    password: string;
  }): Promise<AuthSession> =>
    resolveWrite(
      () => api.register(data),
      () => localStorageApi.register(data),
    ),

  logout: async (sessionToken: string): Promise<void> =>
    resolveWrite(
      () => api.logout(sessionToken),
      () => localStorageApi.logout(sessionToken),
    ),

  forgotPassword: async (email: string): Promise<void> =>
    resolveWrite(
      () => api.forgotPassword(email),
      () => localStorageApi.forgotPassword(email),
    ),

  getProfile: async (): Promise<UserProfile> =>
    fallbackRead(
      () => api.getProfile(),
      () => localStorageApi.getProfile(),
    ),

  updateProfile: async (data: { name?: string; email?: string }): Promise<UserProfile> =>
    resolveWrite(
      () => api.updateProfile(data),
      () => localStorageApi.updateProfile(data),
    ),

  deleteAccount: async (): Promise<void> =>
    resolveWrite(
      () => api.deleteAccount(),
      () => localStorageApi.deleteAccount(),
    ),

  getSettings: async (): Promise<UserSettings> =>
    fallbackRead(
      () => api.getSettings(),
      () => localStorageApi.getSettings(),
    ),

  updateSettings: async (data: Partial<UserSettings>): Promise<UserSettings> =>
    resolveWrite(
      () => api.updateSettings(data),
      () => localStorageApi.updateSettings(data),
    ),

  // --- Transactions ---
  getTransactions: async (): Promise<Transaction[]> =>
    fallbackRead(
      () => api.getTransactions(),
      () => localStorageApi.getTransactions(),
    ),

  createTransaction: async (data: Partial<Transaction>) =>
    resolveWrite(
      () => api.createTransaction(data),
      () => localStorageApi.createTransaction(data),
    ),

  updateTransaction: async (id: number, data: Partial<Transaction>) =>
    resolveWrite(
      () => api.updateTransaction(id, data),
      () => localStorageApi.updateTransaction(id, data),
    ),

  deleteTransaction: async (id: number) =>
    resolveWrite(
      () => api.deleteTransaction(id),
      () => localStorageApi.deleteTransaction(id),
    ),

  // --- Goals ---
  getGoalsStatus: async (): Promise<Goal[]> =>
    fallbackRead(
      () => api.getGoalsStatus(),
      () => localStorageApi.getGoalsStatus(),
    ),

  createGoal: async (data: Partial<Goal>) =>
    resolveWrite(
      () => api.createGoal(data),
      () => localStorageApi.createGoal(data),
    ),

  depositGoal: async (id: number, amount: number) =>
    resolveWrite(
      () => api.depositGoal(id, amount),
      () => localStorageApi.depositGoal(id, amount),
    ),

  completeGoal: async (id: number) =>
    resolveWrite(
      () => api.completeGoal(id),
      () => localStorageApi.completeGoal(id),
    ),

  deleteGoal: async (id: number) =>
    resolveWrite(
      () => api.deleteGoal(id),
      () => localStorageApi.deleteGoal(id),
    ),

  // --- Dashboard / Insights / Charts ---
  getSummary: async (): Promise<DashboardSummary> =>
    fallbackRead(
      () => api.getSummary(),
      () => localStorageApi.getSummary(),
    ),

  getInsights: async (): Promise<InsightData | null> =>
    fallbackRead(
      () => api.getInsights(),
      () => localStorageApi.getInsights(),
    ),

  getChartData: async (): Promise<ChartDataPoint[]> =>
    fallbackRead(
      () => api.getChartData(),
      () => localStorageApi.getChartData(),
    ),

  // --- Importação de extrato ---
  // Só CSV tem paridade no modo local por enquanto — OFX continua
  // exigindo o backend (ver checagem de extensão em
  // src/app/transactions/import/page.tsx).
  previewImport: async (file: File): Promise<ImportPreviewResponse> =>
    resolveWrite(
      () => api.previewImport(file),
      () => localStorageApi.previewImport(file),
    ),

  confirmImport: async (
    batchId: number,
    rows: ImportConfirmRow[],
  ): Promise<ImportConfirmResponse> =>
    resolveWrite(
      () => api.confirmImport(batchId, rows),
      () => localStorageApi.confirmImport(batchId, rows),
    ),

  getImportBatches: async (): Promise<ImportBatchSummary[]> =>
    fallbackRead(
      () => api.getImportBatches(),
      () => localStorageApi.getImportBatches(),
    ),
};

export const storageNotificationsService = {
  list: async (
    params: ListNotificationsRequest,
  ): Promise<ListNotificationsResponse> =>
    fallbackRead(
      () => api.request<ListNotificationsResponse>(
        "/notifications",
        { method: "GET" },
        params,
      ),
      () => localStorageNotificationsService.list(params),
    ),

  markAsRead: async (id: number): Promise<MarkNotificationAsReadResponse> =>
    resolveWrite(
      () => api.request<MarkNotificationAsReadResponse>(
        `/notifications/${id}/read`,
        { method: "POST" },
      ),
      () => localStorageNotificationsService.markAsRead(id),
    ),

  markAllAsRead: async (
    params: MarkAllNotificationsAsReadRequest,
  ): Promise<MarkAllNotificationsAsReadResponse> =>
    resolveWrite(
      () => api.request<MarkAllNotificationsAsReadResponse>(
        "/notifications/read-all",
        { method: "POST" },
        params,
      ),
      () => localStorageNotificationsService.markAllAsRead(params),
    ),
};

export function useStorageMode(): StorageMode | null {
  const [mode, setModeState] = useState<StorageMode | null>(currentMode);

  useEffect(() => {
    let cancelled = false;
    const unsub = subscribeStorageMode((next) => {
      if (!cancelled) setModeState(next);
    });
    checkBackendAvailability().then((next) => {
      if (!cancelled) setModeState(next);
    });
    return () => {
      cancelled = true;
      unsub();
    };
  }, []);

  return mode;
}
