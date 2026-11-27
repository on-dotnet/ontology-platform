import { describe, expect, it } from 'vitest';

import { formatDataDateTime } from './format';

describe('formatDataDateTime', () => {
  it('shows a wall-clock time as written, to the second', () => {
    expect(formatDataDateTime('2024-03-10T02:30:45', 'zh-CN')).toBe('2024年3月10日 02:30:45');
    expect(formatDataDateTime('2024-03-10 02:30', 'zh-CN')).toBe('2024年3月10日 02:30:00');
    // Fractions beyond milliseconds are cut, not rounded into the next second.
    expect(formatDataDateTime('2024-03-10T02:30:45.9999999', 'zh-CN')).toBe('2024年3月10日 02:30:45');
  });

  it('reads every way a source writes the offset as the same instant', () => {
    const expected = formatDataDateTime('2024-03-01T16:30:05Z', 'zh-CN');
    for (const value of ['2024-03-02T00:30:05+08:00', '2024-03-02T00:30:05+0800', '2024-03-02 00:30:05+08', '2024-03-01T16:30:05z']) {
      expect(formatDataDateTime(value, 'zh-CN')).toBe(expected);
    }
  });

  it('keeps values it cannot read as they are', () => {
    for (const value of ['2024-03-10T25:00:00', '2024-03-10T02:30:05+99:99', '下午三点', '2024-03-10']) {
      expect(formatDataDateTime(value, 'zh-CN')).toBe(value);
    }
  });
});
