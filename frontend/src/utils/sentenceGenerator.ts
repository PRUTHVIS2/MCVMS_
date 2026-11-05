import type { RegisteredActionSpec } from '../types';

/**
 * Format an array of day identifiers ('mon', 'tue', etc.) into a concise human-readable string.
 * e.g. ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'] -> 'Mon-Sat'
 *      ['mon', 'tue', 'wed', 'thu', 'fri'] -> 'Mon-Fri'
 *      ['sat', 'sun'] -> 'Sat-Sun'
 */
export function formatScheduleDays(days?: string[]): string {
  if (!days || days.length === 0) return '';
  const d = days.map((x) => x.toLowerCase());
  const allDays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

  if (d.length === 7 && allDays.every((x) => d.includes(x))) {
    return 'Daily';
  }
  if (d.length === 6 && ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'].every((x) => d.includes(x))) {
    return 'Mon-Sat';
  }
  if (d.length === 5 && ['mon', 'tue', 'wed', 'thu', 'fri'].every((x) => d.includes(x))) {
    return 'Mon-Fri';
  }
  if (d.length === 2 && d.includes('sat') && d.includes('sun')) {
    return 'Sat-Sun';
  }

  // Capitalize each day
  return days
    .map((day) => day.charAt(0).toUpperCase() + day.slice(1).toLowerCase())
    .join(', ');
}

/**
 * Format an ISO date (YYYY-MM-DD) or display date string to dd/mm/yyyy.
 */
export function formatDateDisplay(d?: string | null): string {
  if (!d) return '';
  const m = d.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) {
    return `${m[3]}/${m[2]}/${m[1]}`;
  }
  return d;
}

/**
 * Generate a clear, plain-language live sentence summary for a registered action rule.
 * Docs reference: docs/08_API_AND_UI.md s4
 * Example: "Raise a CRITICAL alert if a truck or bus stays in 'Loading bay' for 2 s, Mon-Sat 09:00-17:00"
 */
export function generateRuleSentence(spec: Partial<RegisteredActionSpec>, zoneName: string): string {
  const severity = spec.response?.severity?.toUpperCase() || 'CRITICAL';
  const zName = zoneName.trim() ? `'${zoneName.trim()}'` : 'the zone';

  // 1. Subject description
  let subjectDesc = 'an object';
  const kind = spec.subject?.kind || 'vehicle';
  const where = spec.subject?.where || [];

  if (kind === 'vehicle') {
    const isHeavy = where.some((w) => w.attr === 'heavy' && (w.value === true || w.value === 'true'));
    const isUnregistered = where.some((w) => w.attr === 'registry_status' && w.value === 'unregistered');
    const categoryCond = where.find((w) => w.attr === 'category');

    if (isHeavy) {
      subjectDesc = 'a truck or bus';
    } else if (isUnregistered) {
      subjectDesc = 'an unregistered vehicle';
    } else if (categoryCond) {
      subjectDesc = `a ${categoryCond.value}`;
    } else {
      subjectDesc = 'a vehicle';
    }
  } else if (kind === 'person') {
    const isNoId = where.some((w) => w.attr === 'id_state' && w.value === 'not_wearing');
    if (isNoId) {
      subjectDesc = 'a person without a visible ID card';
    } else {
      subjectDesc = 'a person';
    }
  }

  // 2. Trigger action description
  let triggerDesc = `enters ${zName}`;
  const tmpl = spec.trigger?.template || 'presence';

  if (tmpl === 'presence') {
    const minSec = spec.trigger?.min_seconds;
    if (minSec && minSec > 0) {
      triggerDesc = `stays in ${zName} for ${minSec} s`;
    } else {
      triggerDesc = `enters ${zName}`;
    }
  } else if (tmpl === 'dwell') {
    const dwellSec = spec.trigger?.dwell_seconds ?? spec.trigger?.min_seconds ?? 60;
    triggerDesc = `dwells in ${zName} for longer than ${dwellSec} s`;
  } else if (tmpl === 'line_crossing') {
    triggerDesc = `crosses line ${zName}`;
  } else if (tmpl === 'count_threshold') {
    const count = spec.trigger?.count_threshold ?? 5;
    triggerDesc = `more than ${count} subjects are present in ${zName}`;
  }

  // Combine subject and trigger
  let core = '';
  if (tmpl === 'count_threshold') {
    const pluralSubject = kind === 'vehicle' ? 'vehicles' : 'people';
    const count = spec.trigger?.count_threshold ?? 5;
    core = `more than ${count} ${pluralSubject} are present in ${zName}`;
  } else {
    core = `${subjectDesc} ${triggerDesc}`;
  }

  // 3. Schedule (docs/04 s5: omit for always armed)
  let schedulePart = '';
  const daysStr = formatScheduleDays(spec.schedule?.days);
  const fromTime = spec.schedule?.from;
  const toTime = spec.schedule?.to;

  if (daysStr && fromTime && toTime) {
    schedulePart = `, ${daysStr} ${fromTime}-${toTime}`;
  } else if (fromTime && toTime) {
    schedulePart = `, ${fromTime}-${toTime}`;
  } else if (daysStr) {
    schedulePart = `, ${daysStr}`;
  } else {
    schedulePart = ', at all times';
  }

  // 4. Active date validity (formatted as dd/mm/yyyy per requirements)
  let validPart = '';
  const fromDateDisp = formatDateDisplay(spec.valid?.from_date);
  const untilDateDisp = formatDateDisplay(spec.valid?.until_date);

  if (fromDateDisp && untilDateDisp) {
    validPart = ` (active ${fromDateDisp} to ${untilDateDisp})`;
  } else if (fromDateDisp) {
    validPart = ` (active from ${fromDateDisp})`;
  } else if (untilDateDisp) {
    validPart = ` (active until ${untilDateDisp})`;
  }

  return `Raise a ${severity} alert if ${core}${schedulePart}${validPart}.`;
}
