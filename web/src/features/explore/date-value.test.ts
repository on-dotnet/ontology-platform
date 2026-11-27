import { describe, expect, it } from 'vitest';

import { checkDateValue } from './date-value';

describe('checkDateValue', () => {
  // The spellings the server's query values accept after the `T`.
  it.each([
    '08', '0830', '083000', '08:30', '08:30:00', '08:30:00.5', '08:30:00,123456', '08:30:00.1234560000',
    '08:30Z', '08:30+08', '08:30+0800', '08:30-08:00', '08:30+08:00:00', ' 08:30 ',
  ])('accepts the time "%s"', (time) => {
    expect(checkDateValue(`2024-02-29T${time}`, true, true)).toMatchObject({ badDate: false, badTime: false });
  });

  it.each([
    '8:30', '24:00', '08:60', '08:30:60', '08:30:00.1234567', '08.5', 'Z', '08:30+8', '08:30+24', '08:30 +08:00',
  ])('refuses the time "%s"', (time) => {
    expect(checkDateValue(`2024-02-29T${time}`, true, false).badTime).toBe(true);
  });

  it.each(['', '2024-02-30', '2023-02-29', '0000-01-01', '2024-2-9'])('refuses the date "%s"', (date) => {
    expect(checkDateValue(date, false, false).badDate).toBe(true);
  });
});
