import { describe, it, expect } from 'vitest';
import { formatLocalTime, formatLocalDateTime, formatLocalDate, TIMEZONE } from './date';

describe('date utils (Asia/Kolkata timezone)', () => {
  it('formats epoch milliseconds to local HH:mm:ss in Asia/Kolkata', () => {
    // 2026-11-04 05:00:00 UTC = 1793768400000 -> 10:30:00 in Asia/Kolkata (+05:30)
    const epochMs = 1793768400000;
    const formatted = formatLocalTime(epochMs);
    expect(formatted).toBe('10:30:00');
  });

  it('handles string timestamps gracefully without showing Invalid Date', () => {
    const epochMsStr = '1793768400000';
    expect(formatLocalTime(epochMsStr)).toBe('10:30:00');
  });

  it('returns empty string for invalid, zero, or null timestamps', () => {
    expect(formatLocalTime(null)).toBe('');
    expect(formatLocalTime(undefined)).toBe('');
    expect(formatLocalTime(0)).toBe('');
    expect(formatLocalTime('not-a-number')).toBe('');
  });

  it('formats full date and time in Asia/Kolkata', () => {
    const epochMs = 1793768400000;
    const formatted = formatLocalDateTime(epochMs);
    expect(formatted).toContain('10:30:00');
    expect(formatted).toContain('2026');
  });

  it('formats date only in Asia/Kolkata', () => {
    const epochMs = 1793768400000;
    const formatted = formatLocalDate(epochMs);
    expect(formatted).toContain('2026');
  });
});

