import { describe, expect, it } from "vitest";
import { decodeSourceBytes } from "./source-bytes";
describe("权威UTF8源字节", () => {
  it.each(["\uFEFF# Synthetic\r\n", "# Synthetic\r\n中文：合成事实\r\n", "", "# Synthetic\n普通源\n"])("BOM/CRLF/中文/空源逐字节roundtrip", value => {
    const bytes = new TextEncoder().encode(value);
    expect(new TextEncoder().encode(decodeSourceBytes(bytes))).toEqual(bytes);
  });
  it.each([[0xc3, 0x28], [0xff], [0xed, 0xa0, 0x80], [0xe4, 0xb8]].map(bytes => ({ bytes })))("非法UTF8明确拒绝且不产生替代字符", ({ bytes }) => {
    expect(() => decodeSourceBytes(new Uint8Array(bytes))).toThrow("invalid_source_utf8");
  });
});
