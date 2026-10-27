/** 严格UTF8解码保留BOM及CRLF；非法字节拒绝，不用替代字符污染权威源。 */
export function decodeSourceBytes(bytes: BufferSource): string {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    throw new Error("invalid_source_utf8");
  }
}

/** textarea将换行规范化为LF；无实际文本变更时继续使用权威源的原字节表示。 */
export function preserveEditorSource(source: string, edited: string): string {
  return source.replace(/\r\n?/g, "\n") === edited ? source : edited;
}
