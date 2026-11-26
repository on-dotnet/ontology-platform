import { useTranslation } from 'react-i18next';

export function MetricsPanel(_props: { ontologyId: string }) {
  const { t } = useTranslation();
  return <p className="text-sm text-muted-foreground">{t('metrics.placeholder')}</p>;
}
