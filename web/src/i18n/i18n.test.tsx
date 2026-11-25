import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useTranslation } from 'react-i18next';
import { describe, expect, it } from 'vitest';

import { LanguageSelector } from '@/features/settings/preference-controls';
import { renderWithProviders } from '@/test/utils';

import { LOCALE_STORAGE_KEY, matchLocale, resources } from './index';
import en from './locales/en.json';
import zhCN from './locales/zh-CN.json';

function NavProbe() {
  const { t } = useTranslation();
  return <p>{t('nav.workbench')}</p>;
}

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => flattenKeys(child, prefix ? `${prefix}.${key}` : key));
}

describe('i18n', () => {
  it('switches the interface language and remembers it', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <LanguageSelector />
        <NavProbe />
      </>,
    );
    expect(screen.getByText('工作台')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'English' }));
    expect(await screen.findByText('Workbench')).toBeInTheDocument();
    expect(screen.queryByText('工作台')).not.toBeInTheDocument();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it('maps browser languages and falls back to Simplified Chinese', () => {
    expect(matchLocale('zh-TW')).toBe('zh-CN');
    expect(matchLocale('en-GB')).toBe('en');
    expect(matchLocale('fr-FR')).toBeUndefined();
  });

  it('has the same keys in every locale', () => {
    // Everything i18next gets, including the per-namespace files of locales/<locale>/.
    expect(flattenKeys(resources.en.translation).sort()).toEqual(flattenKeys(resources['zh-CN'].translation).sort());
  });

  it('adds the per-namespace files as their own top-level keys', () => {
    const added = ['datasources', 'bindings', 'explore', 'tokens', 'mcp'];
    for (const locale of [resources['zh-CN'].translation, resources.en.translation]) {
      expect(Object.keys(locale)).toEqual(expect.arrayContaining(added));
    }
    for (const namespace of added) {
      expect(namespace in zhCN || namespace in en).toBe(false);
    }
  });
});
