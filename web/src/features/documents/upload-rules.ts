/** File types the platform can parse (spec 001 §3.2). */
export const ACCEPTED_EXTENSIONS = ['docx', 'xlsx', 'pdf', 'md', 'txt'] as const;
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((extension) => `.${extension}`).join(',');
/** Upload limit per file; the server enforces the same limit. */
export const MAX_UPLOAD_MB = 20;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

export type RejectionReason = 'type' | 'size' | 'empty';

export interface UploadRejection {
  fileName: string;
  reason: RejectionReason;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

/** Splits files into those worth sending and those rejected before upload (type, size, empty). */
export function validateFiles(files: readonly File[]): { accepted: File[]; rejected: UploadRejection[] } {
  const accepted: File[] = [];
  const rejected: UploadRejection[] = [];
  for (const file of files) {
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(file.name))) {
      rejected.push({ fileName: file.name, reason: 'type' });
    } else if (file.size > MAX_UPLOAD_BYTES) {
      rejected.push({ fileName: file.name, reason: 'size' });
    } else if (file.size === 0) {
      rejected.push({ fileName: file.name, reason: 'empty' });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}
