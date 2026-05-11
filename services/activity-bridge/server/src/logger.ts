type LogLevel = "info" | "warn" | "error";

function log(level: LogLevel, message: string, meta?: unknown) {
  const entry = {
    level,
    message,
    time: new Date().toISOString(),
    ...(meta == null ? {} : { meta })
  };
  console.log(JSON.stringify(entry));
}

export const logger = {
  info: (message: string, meta?: unknown) => log("info", message, meta),
  warn: (message: string, meta?: unknown) => log("warn", message, meta),
  error: (message: string, meta?: unknown) => log("error", message, meta)
};
