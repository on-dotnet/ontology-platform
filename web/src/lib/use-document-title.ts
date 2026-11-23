import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

/** Sets `<title>` to "<page> · <product name>" in the current language. */
export function useDocumentTitle(page: string): void {
  const { t } = useTranslation();
  useEffect(() => {
    document.title = page ? t('app.documentTitle', { page }) : t('app.name');
  }, [page, t]);
}
