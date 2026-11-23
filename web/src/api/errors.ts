/** Error codes produced by the client itself (no response from the server). */
export const NETWORK_ERROR_CODE = 'network.unreachable';

interface ApiErrorInit {
  status: number;
  code: string;
  title?: string | undefined;
  detail?: string | undefined;
  cause?: unknown;
}

/**
 * A failed API call. `code` is the stable machine code from the problem+json body
 * (e.g. `auth.invalid_credentials`); the UI maps it to localized text and never shows `title`/`detail`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string | undefined;
  readonly detail: string | undefined;

  constructor({ status, code, title, detail, cause }: ApiErrorInit) {
    super(`${code} (HTTP ${status})`, { cause });
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.title = title;
    this.detail = detail;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

function readString(source: Record<string, unknown>, key: string): string | undefined {
  const value = source[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/** Builds an ApiError from an RFC 9457 body; bodies without a `code` get `http.<status>`. */
export function problemToError(status: number, body: unknown): ApiError {
  const problem = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
  return new ApiError({
    status,
    code: readString(problem, 'code') ?? `http.${status}`,
    title: readString(problem, 'title'),
    detail: readString(problem, 'detail'),
  });
}
