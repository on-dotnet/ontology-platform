/** File types the platform can parse (spec 001 §3.2). */
export const ACCEPTED_EXTENSIONS = ['docx', 'xlsx', 'pdf', 'md', 'txt'] as const;
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((extension) => `.${extension}`).join(',');
/** Upload limit per file; the server enforces the same limit. */
export const MAX_UPLOAD_MB = 20;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
/** Recognition limits per document (`documents.too_long`, `documents.too_many_pages`); the server enforces them. */
export const MAX_RECOGNIZED_CHARS = 200_000;
export const MAX_SCANNED_PAGES = 100;

export type RejectionReason = 'type' | 'size' | 'empty' | 'chars';

export interface UploadRejection {
  fileName: string;
  reason: RejectionReason;
  /** Characters counted in the file, for `chars`. */
  count?: number;
}

/** Text files are counted before uploading; other formats are counted by the server after parsing. */
const COUNTED_EXTENSIONS = ['md', 'txt'];

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

/** Characters as the server counts them (code points), decoding like it does: UTF-8, else GB 18030. */
export async function countCharacters(file: File): Promise<number | undefined> {
  const data = await file.arrayBuffer();
  for (const encoding of ['utf-8', 'gb18030']) {
    try {
      const text = new TextDecoder(encoding, { fatal: true }).decode(data);
      // Decoded text has no lone surrogates, so each low surrogate ends a pair: one code point.
      return text.length - (text.match(/[\uDC00-\uDFFF]/g)?.length ?? 0);
    } catch {
      // Not this encoding (or not supported here): try the next one.
    }
  }
  // Undecodable: the server reports it as unreadable.
  return undefined;
}

/** Splits files into those worth sending and those rejected before upload (type, size, empty, characters). */
export async function validateFiles(files: readonly File[]): Promise<{ accepted: File[]; rejected: UploadRejection[] }> {
  const accepted: File[] = [];
  const rejected: UploadRejection[] = [];
  for (const file of files) {
    const extension = extensionOf(file.name);
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extension)) {
      rejected.push({ fileName: file.name, reason: 'type' });
    } else if (file.size > MAX_UPLOAD_BYTES) {
      rejected.push({ fileName: file.name, reason: 'size' });
    } else if (file.size === 0) {
      rejected.push({ fileName: file.name, reason: 'empty' });
    } else {
      const count = COUNTED_EXTENSIONS.includes(extension) ? await countCharacters(file) : undefined;
      if (count !== undefined && count > MAX_RECOGNIZED_CHARS) {
        rejected.push({ fileName: file.name, reason: 'chars', count });
      } else {
        accepted.push(file);
      }
    }
  }
  return { accepted, rejected };
}
