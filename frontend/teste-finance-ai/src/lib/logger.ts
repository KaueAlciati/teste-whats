type LogMeta = Record<string, unknown>;

type Logger = {
  debug: (message: string, meta?: LogMeta) => void;
  info: (message: string, meta?: LogMeta) => void;
  warn: (message: string, meta?: LogMeta) => void;
  error: (message: string, meta?: LogMeta) => void;
};

const isDev = process.env.NODE_ENV !== "production";

function formatMeta(meta?: LogMeta) {
  if (!meta) return undefined;
  return Object.keys(meta).length ? meta : undefined;
}

export const logger: Logger = {
  debug: (message, meta) => {
    if (!isDev) return;
    const m = formatMeta(meta);
    if (m) console.debug(message, m);
    else console.debug(message);
  },
  info: (message, meta) => {
    const m = formatMeta(meta);
    if (m) console.info(message, m);
    else console.info(message);
  },
  warn: (message, meta) => {
    const m = formatMeta(meta);
    if (m) console.warn(message, m);
    else console.warn(message);
  },
  error: (message, meta) => {
    const m = formatMeta(meta);
    if (m) console.error(message, m);
    else console.error(message);
  },
};
