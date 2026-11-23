import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ThemeSelector } from '@/features/settings/preference-controls';
import { renderWithProviders } from '@/test/utils';

import { THEME_STORAGE_KEY } from './theme';

describe('theme preference', () => {
  it('switches the html class and persists the choice', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThemeSelector />);

    // Default is "follow system"; the test environment reports a light system theme.
    expect(screen.getByRole('radio', { name: '跟随系统' })).toBeChecked();
    expect(document.documentElement).not.toHaveClass('dark');

    await user.click(screen.getByRole('radio', { name: '深色' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await user.click(screen.getByRole('radio', { name: '浅色' }));
    expect(document.documentElement).not.toHaveClass('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('restores a saved preference on start', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderWithProviders(<ThemeSelector />);
    expect(screen.getByRole('radio', { name: '深色' })).toBeChecked();
    expect(document.documentElement).toHaveClass('dark');
  });
});
