/** Saves text as a file through a temporary object URL (the response is already in memory). */
export function downloadText(filename: string, text: string, type = 'text/turtle;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
  // Revoke after the click has been handled.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
