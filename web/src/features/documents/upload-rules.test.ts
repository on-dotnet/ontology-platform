import { describe, expect, it } from 'vitest';

import { countCharacters, MAX_RECOGNIZED_CHARS, validateFiles } from './upload-rules';

/** "钢" in GBK / GB 18030. */
const GBK_STEEL = [0xb8, 0xd6];

function gbkFile(name: string, characters: number): File {
  const bytes = new Uint8Array(characters * 2);
  for (let index = 0; index < characters; index += 1) bytes.set(GBK_STEEL, index * 2);
  return new File([bytes], name);
}

describe('character counting before upload', () => {
  it('counts characters like the server: code points, GB 18030 when not UTF-8, no BOM, CRLF as two', async () => {
    expect(await countCharacters(gbkFile('目录.txt', 3))).toBe(3);
    // A CJK Extension B character is two UTF-16 code units but one character.
    expect(await countCharacters(new File(['𠀀𠀀'], 'a.txt'))).toBe(2);
    expect(await countCharacters(new File(['﻿炉次'], 'a.txt'))).toBe(2);
    expect(await countCharacters(new File(['a\r\nb'], 'a.txt'))).toBe(4);
  });

  it('refuses a GBK text over the limit and accepts long Extension B text within it', async () => {
    const { accepted, rejected } = await validateFiles([
      gbkFile('手册.txt', MAX_RECOGNIZED_CHARS + 1),
      new File(['𠀀'.repeat(MAX_RECOGNIZED_CHARS)], '字表.md'),
    ]);
    expect(rejected).toEqual([{ fileName: '手册.txt', reason: 'chars', count: MAX_RECOGNIZED_CHARS + 1 }]);
    expect(accepted.map((file) => file.name)).toEqual(['字表.md']);
  });

  it('leaves a file it cannot read to the server instead of dropping the whole choice', async () => {
    const unreadable = new File(['x'.repeat(MAX_RECOGNIZED_CHARS + 1)], '已移动.txt');
    Object.defineProperty(unreadable, 'arrayBuffer', { value: () => Promise.reject(new DOMException('gone', 'NotReadableError')) });
    const { accepted, rejected } = await validateFiles([unreadable, new File(['炉次'], '规程.md')]);
    expect(rejected).toEqual([]);
    expect(accepted.map((file) => file.name)).toEqual(['已移动.txt', '规程.md']);
  });
});
