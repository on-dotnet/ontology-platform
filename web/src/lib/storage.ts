/**
 * localStorage access that never throws: storage can be unavailable (private mode,
 * blocked site data, quota). Preferences then simply fall back to defaults.
 */
export const storage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Ignore: the preference only lasts for this page view.
    }
  },
};
