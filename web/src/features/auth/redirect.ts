/**
 * Turns `?redirect=` into a safe post-login target: it must resolve to this origin, and only its
 * path, query and hash are kept. The URL parser handles tricks such as `/\t/evil.example` (tabs are
 * stripped), `/\evil.example` (backslash counts as a slash) and `javascript:` URLs.
 */
export function safeRedirect(value: unknown, origin: string = window.location.origin): string | undefined {
  if (typeof value !== 'string' || value === '') return undefined;

  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return undefined;
  }
  if (url.origin !== origin) return undefined;

  const target = `${url.pathname}${url.search}${url.hash}`;
  // `//host` would be read as protocol-relative by the browser; the login page itself would loop.
  if (target.startsWith('//')) return undefined;
  if (url.pathname === '/login' || url.pathname.startsWith('/login/')) return undefined;
  return target;
}
