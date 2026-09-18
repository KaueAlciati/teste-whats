export type AppErrorCode =
  | "UNKNOWN"
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "SERVER_ERROR";

export type AppErrorOptions = {
  code?: AppErrorCode;
  status?: number;
  details?: unknown;
  cause?: unknown;
};

export class AppError extends Error {
  readonly code: AppErrorCode;
  readonly status?: number;
  readonly details?: unknown;
  readonly cause?: unknown;

  constructor(message: string, options: AppErrorOptions = {}) {
    super(message);
    this.name = "AppError";
    this.code = options.code ?? "UNKNOWN";
    this.status = options.status;
    this.details = options.details;
    this.cause = options.cause;
  }
}

export function isAppError(error: unknown): error is AppError {
  return error instanceof AppError;
}
