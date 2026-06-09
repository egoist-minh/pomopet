export interface LogEntry {
  timestamp: string;
  type: 'log' | 'error' | 'warn';
  message: string;
}

type OriginalConsole = {
  log: typeof console.log;
  error: typeof console.error;
  warn: typeof console.warn;
};

const logHistory: LogEntry[] = [];
let originalConsole: OriginalConsole | null = null;
let initialized = false;

function formatMessage(args: unknown[]): string {
  return args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      if (arg instanceof Error) return `${arg.name}: ${arg.message}\n${arg.stack ?? ''}`;
      try {
        return JSON.stringify(arg, null, 2);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

function interceptConsole() {
  if (typeof window === 'undefined' || initialized) return;
  if (originalConsole) return;

  originalConsole = {
    log: console.log.bind(console),
    error: console.error.bind(console),
    warn: console.warn.bind(console),
  };

  console.log = (...args: unknown[]) => {
    logHistory.push({ timestamp: new Date().toISOString(), type: 'log', message: formatMessage(args) });
    originalConsole!.log(...args);
  };

  console.error = (...args: unknown[]) => {
    logHistory.push({ timestamp: new Date().toISOString(), type: 'error', message: formatMessage(args) });
    originalConsole!.error(...args);
  };

  console.warn = (...args: unknown[]) => {
    logHistory.push({ timestamp: new Date().toISOString(), type: 'warn', message: formatMessage(args) });
    originalConsole!.warn(...args);
  };

  initialized = true;
}

export function initializeLogger(): void {
  interceptConsole();
}

export function getLogHistory(): LogEntry[] {
  return [...logHistory];
}

export function downloadLogs(): void {
  if (typeof window === 'undefined') return;

  const logs = getLogHistory();
  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  const filename = `frontend-system-log-${dateStr}.txt`;

  const content = logs
    .map((entry) => `[${entry.timestamp}] [${entry.type.toUpperCase()}] ${entry.message}`)
    .join('\n');

  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
