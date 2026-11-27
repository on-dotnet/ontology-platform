/** A date or dateTime filter value is edited as a date plus an optional `T…` time part. */
function splitDateValue(value: string): { date: string; time: string } {
  const at = value.indexOf('T');
  return at < 0 ? { date: value, time: '' } : { date: value.slice(0, at), time: value.slice(at + 1) };
}

export function joinDateValue(date: string, time: string): string {
  return time ? `${date}T${time}` : date;
}

export function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000-')) return false;
  const date = new Date(value);
  // Date normalizes some impossible days into the next month.
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// The same grammar as the server's query values, so nothing it accepts is refused here.
const clockPattern = String.raw`(?:[01]\d|2[0-3])(?::?[0-5]\d(?::?[0-5]\d(?:[.,]\d{1,6}0*)?)?)?`;
const timePattern = new RegExp(`^${clockPattern}(?:Z|[+-]${clockPattern})?$`);

export function checkDateValue(value: string, withTime: boolean, timeRequired: boolean) {
  const { date, time } = splitDateValue(value);
  const clock = time.trim();
  const badTime = withTime && (clock ? !timePattern.test(clock) : timeRequired);
  return { date, time, clock, badDate: !isCalendarDate(date), badTime };
}
