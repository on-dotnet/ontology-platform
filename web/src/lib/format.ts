const RECENT_SECONDS = 7 * 24 * 3600;

const UNITS: readonly (readonly [Intl.RelativeTimeFormatUnit, number])[] = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
];

function parse(iso: string): number | undefined {
  const time = new Date(iso).getTime();
  return Number.isNaN(time) ? undefined : time;
}

/** Full local date and time, e.g. "2026年11月22日 14:05". */
export function formatDateTime(iso: string, locale: string): string {
  const time = parse(iso);
  if (time === undefined) return '—';
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(time);
}

// Offsets come as +08:00, +0800 or, in PostgreSQL's text output, just +08.
const DATA_DATE_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|[+-]\d{2}(?::?\d{2})?)?$/i;

/**
 * A date and time value read from a data source, to the second (#79).
 * A value with an offset is an instant and shows in local time; one without is a wall-clock time
 * the source stored as written, so it shows unchanged in the same format. Anything else is kept as is.
 */
export function formatDataDateTime(value: string, locale: string): string {
  const match = DATA_DATE_TIME.exec(value);
  if (!match) return value;
  const [, date = '', minutes = '', seconds = '00', fraction = '', zone] = match;
  // Sources write up to microseconds; not every engine parses more than milliseconds.
  const millis = fraction.padEnd(3, '0').slice(0, 3);
  const offset = zone ? zone.toUpperCase().replace(/^([+-]\d{2}):?(\d{2})?$/, (_, hours: string, minutes?: string) => `${hours}:${minutes ?? '00'}`) : 'Z';
  const time = Date.parse(`${date}T${minutes}:${seconds}.${millis}${offset}`);
  if (Number.isNaN(time)) return value;
  const options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'medium' };
  return new Intl.DateTimeFormat(locale, zone ? options : { ...options, timeZone: 'UTC' }).format(time);
}

/** Relative time for the last seven days ("3 分钟前"), the local date after that (ui-guidelines §6). */
export function formatRecent(iso: string, locale: string, now: number = Date.now()): string {
  const time = parse(iso);
  if (time === undefined) return '—';
  const seconds = Math.round((time - now) / 1000);
  if (Math.abs(seconds) >= RECENT_SECONDS) return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(time);
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, 'second');
}

/** File size with at most one decimal, e.g. "1.2 MB". */
export function formatBytes(bytes: number, locale: string): string {
  const units = ['B', 'KB', 'MB', 'GB'] as const;
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  const digits = index === 0 ? 0 : 1;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value)} ${units[index] ?? 'B'}`;
}

/** Whole percent, e.g. 0.834 → "83%". */
export function formatPercent(ratio: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(ratio);
}

/** Whole number with grouping, e.g. 200000 → "200,000". */
export function formatCount(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
}
