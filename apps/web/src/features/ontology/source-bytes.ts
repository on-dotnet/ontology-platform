/** 严格UTF8解码保留BOM及CRLF；非法字节拒绝，不用替代字符污染权威源。 */
export function decodeSourceBytes(bytes: BufferSource): string {
  try { return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes); }
  catch { throw new Error("invalid_source_utf8"); }
}
