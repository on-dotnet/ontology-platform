// Applies the saved theme before first paint to avoid a light/dark flash.
// Keep the storage key and values in sync with src/theme/theme.ts.
(function () {
  var preference = 'system';
  try {
    var saved = window.localStorage.getItem('op.theme');
    if (saved === 'light' || saved === 'dark' || saved === 'system') preference = saved;
  } catch {
    // Storage unavailable (private mode, blocked cookies): fall back to the system theme.
  }
  var prefersDark =
    typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var dark = preference === 'dark' || (preference === 'system' && prefersDark);
  var root = document.documentElement;
  root.classList.toggle('dark', dark);
  root.style.colorScheme = dark ? 'dark' : 'light';
})();
