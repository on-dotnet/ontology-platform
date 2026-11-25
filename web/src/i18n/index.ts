import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { storage } from '@/lib/storage';

import en from './locales/en.json';
import zhCN from './locales/zh-CN.json';

export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

type Messages = Record<string, unknown>;

// Namespaces added from M3 on live in their own files (locales/<locale>/<namespace>.json), so that
// batches working in parallel do not all edit one file. Each file becomes a top-level key of the
// single `translation` namespace: locales/zh-CN/tokens.json is `t('tokens.…')`.
const namespaceFiles = import.meta.glob<Messages>('./locales/*/*.json', { eager: true, import: 'default' });

function withNamespaces(locale: Locale, base: Messages): Messages {
  const merged: Messages = { ...base };
  for (const [path, messages] of Object.entries(namespaceFiles)) {
    const match = /^\.\/locales\/([^/]+)\/([^/]+)\.json$/.exec(path);
    if (!match || match[1] !== locale) continue;
    const namespace = match[2] as string;
    if (namespace in base) throw new Error(`i18n namespace "${namespace}" is already a key of ${locale}.json`);
    merged[namespace] = messages;
  }
  return merged;
}

/** Every message of every locale, as i18next gets them. */
export const resources = {
  'zh-CN': { translation: withNamespaces('zh-CN', zhCN) },
  en: { translation: withNamespaces('en', en) },
} as const;
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
  resources,
  lng: detectLocale(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [...SUPPORTED_LOCALES],
  initAsync: false,
  interpolation: { escapeValue: false },
  react: { useSuspense: false },
});

export default i18n;
