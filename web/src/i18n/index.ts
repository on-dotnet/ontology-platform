import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { storage } from '@/lib/storage';

import en from './locales/en.json';
import zhCN from './locales/zh-CN.json';

export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'zh-CN';
export const LOCALE_STORAGE_KEY = 'op.locale';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** Maps a BCP 47 tag from the browser to a supported locale (any Chinese variant → zh-CN). */
export function matchLocale(tag: string | null | undefined): Locale | undefined {
  const lower = tag?.toLowerCase();
  if (!lower) return undefined;
  if (lower === 'zh' || lower.startsWith('zh-')) return 'zh-CN';
  if (lower === 'en' || lower.startsWith('en-')) return 'en';
  return undefined;
}

/** Saved choice first, then the browser languages, then Simplified Chinese. */
export function detectLocale(): Locale {
  const saved = storage.get(LOCALE_STORAGE_KEY);
  if (isLocale(saved)) return saved;
  const candidates = typeof navigator === 'undefined' ? [] : [...(navigator.languages ?? []), navigator.language];
  for (const tag of candidates) {
    const locale = matchLocale(tag);
    if (locale) return locale;
  }
  return DEFAULT_LOCALE;
}

/** Switches the interface language and remembers the choice. */
export async function changeLocale(locale: Locale): Promise<void> {
  storage.set(LOCALE_STORAGE_KEY, locale);
  await i18n.changeLanguage(locale);
}

export function currentLocale(): Locale {
  return isLocale(i18n.resolvedLanguage) ? i18n.resolvedLanguage : DEFAULT_LOCALE;
}

i18n.on('languageChanged', (language) => {
  if (typeof document !== 'undefined') document.documentElement.lang = language;
});

void i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    en: { translation: en },
  },
  lng: detectLocale(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [...SUPPORTED_LOCALES],
  initAsync: false,
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
});

export default i18n;
