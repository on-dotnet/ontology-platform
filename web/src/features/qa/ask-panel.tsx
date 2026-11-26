import { useTranslation } from 'react-i18next';

export function AskPanel(_props: { ontologyId: string }) {
  const { t } = useTranslation();
  return <p className="text-sm text-muted-foreground">{t('qa.placeholder')}</p>;
}
