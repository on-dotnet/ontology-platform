import { Languages, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { buttonVariants } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip } from '@/components/ui/tooltip';
import { changeLocale, currentLocale, isLocale, SUPPORTED_LOCALES } from '@/i18n';
import { isThemePreference, type ThemePreference } from '@/theme/theme';
import { useTheme } from '@/theme/theme-provider';

const iconButton = buttonVariants({ variant: 'ghost', size: 'icon' });

export const THEME_OPTIONS: readonly { value: ThemePreference; labelKey: string; icon: LucideIcon }[] = [
  { value: 'light', labelKey: 'preferences.themeLight', icon: Sun },
  { value: 'dark', labelKey: 'preferences.themeDark', icon: Moon },
  { value: 'system', labelKey: 'preferences.themeSystem', icon: Monitor },
];

export function LanguageMenu() {
  const { t } = useTranslation();
  const label = t('preferences.switchLanguage');
  return (
    <DropdownMenu>
      <Tooltip content={label} side="bottom">
        <DropdownMenuTrigger aria-label={label} className={iconButton}>
          <Languages aria-hidden />
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent className="min-w-40">
        <DropdownMenuRadioGroup
          value={currentLocale()}
          onValueChange={(value: unknown) => {
            if (isLocale(value)) void changeLocale(value);
          }}
        >
          {SUPPORTED_LOCALES.map((locale) => (
            <DropdownMenuRadioItem key={locale} value={locale} lang={locale}>
              {t(`preferences.languages.${locale}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ThemeMenu() {
  const { t } = useTranslation();
  const { preference, resolved, setPreference } = useTheme();
  const label = t('preferences.switchTheme');
  const TriggerIcon = preference === 'system' ? Monitor : resolved === 'dark' ? Moon : Sun;
  return (
    <DropdownMenu>
      <Tooltip content={label} side="bottom">
        <DropdownMenuTrigger aria-label={label} className={iconButton}>
          <TriggerIcon aria-hidden />
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent className="min-w-40">
        <DropdownMenuRadioGroup
          value={preference}
          onValueChange={(value: unknown) => {
            if (isThemePreference(value)) setPreference(value);
          }}
        >
          {THEME_OPTIONS.map(({ value, labelKey, icon: Icon }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon aria-hidden />
              {t(labelKey)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
