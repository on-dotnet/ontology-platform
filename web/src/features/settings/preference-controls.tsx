import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { THEME_OPTIONS } from '@/components/layout/preference-menus';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { changeLocale, currentLocale, SUPPORTED_LOCALES } from '@/i18n';
import { useTheme } from '@/theme/theme-provider';

export function LanguageSelector() {
  const { t } = useTranslation();
  return (
    <SegmentedControl
      legend={t('preferences.language')}
      value={currentLocale()}
      options={SUPPORTED_LOCALES.map((locale) => ({ value: locale, label: t(`preferences.languages.${locale}`) }))}
      onValueChange={(locale) => void changeLocale(locale)}
    />
  );
}

export function ThemeSelector() {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();
  return (
    <SegmentedControl
      legend={
        <span className="inline-flex items-center gap-1">
          {t('preferences.theme')}
          <InfoTip>{t('preferences.themeSystemHint')}</InfoTip>
        </span>
      }
      value={preference}
      options={THEME_OPTIONS.map(({ value, labelKey, icon: Icon }) => ({
        value,
        label: t(labelKey),
        icon: <Icon aria-hidden />,
      }))}
      onValueChange={setPreference}
    />
  );
}
