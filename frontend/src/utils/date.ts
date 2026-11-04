export const TIMEZONE = 'Asia/Kolkata';

/**
 * Format timestamp (epoch ms) to local 24h time in Asia/Kolkata (HH:mm:ss).
 */
export function formatLocalTime(tsMs?: number | string | null): string {
  if (!tsMs) return '';
  const num = typeof tsMs === 'string' ? Number(tsMs) : tsMs;
  if (isNaN(num) || num <= 0) return '';
  try {
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: TIMEZONE,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(num));
  } catch {
    return '';
  }
}

/**
 * Format timestamp (epoch ms) to local date and time in Asia/Kolkata.
 */
export function formatLocalDateTime(tsMs?: number | string | null): string {
  if (!tsMs) return '';
  const num = typeof tsMs === 'string' ? Number(tsMs) : tsMs;
  if (isNaN(num) || num <= 0) return '';
  try {
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: TIMEZONE,
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(num));
  } catch {
    return '';
  }
}

/**
 * Format timestamp (epoch ms) to date in Asia/Kolkata.
 */
export function formatLocalDate(tsMs?: number | string | null): string {
  if (!tsMs) return '';
  const num = typeof tsMs === 'string' ? Number(tsMs) : tsMs;
  if (isNaN(num) || num <= 0) return '';
  try {
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: TIMEZONE,
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    }).format(new Date(num));
  } catch {
    return '';
  }
}

