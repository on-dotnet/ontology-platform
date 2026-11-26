import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';

export function MetricResult({ result }: { result: components['schemas']['MetricValue'] }) {
  const { t } = useTranslation();
  const display = result.display ?? result.value;
  const unit = result.unit === '%' && display?.trimEnd().endsWith('%') ? null : result.unit;
  const scanned = result.steps.reduce((total, step) => total + step.rows, 0);
  return (
    <div className="space-y-3 p-2">
      <div>
        <p className="text-xs text-muted-foreground">{t('metrics.value')}</p>
        {display === null ? (
          <p>{t(result.reason === 'empty_population' ? 'metrics.emptyPopulation' : 'explore.noValue')}</p>
        ) : (
          <p className="text-xl font-semibold tabular-nums">{display}{unit && <span className="ml-1 text-sm">{unit}</span>}</p>
        )}
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-2">
        {result.aggregate === 'ratio' && <div>
          <dt className="text-muted-foreground">{t('metrics.matched')}</dt><dd className="tabular-nums">{result.matched}</dd>
        </div>}
        <div><dt className="text-muted-foreground">{t('metrics.population')}</dt><dd className="tabular-nums">{result.population}</dd></div>
        <div><dt className="text-muted-foreground">{t('metrics.nulls')}</dt><dd className="tabular-nums">{result.nulls}</dd></div>
        <div><dt className="text-muted-foreground">{t('metrics.scanned')}</dt><dd className="tabular-nums">{scanned}</dd></div>
      </dl>
      <p className="text-xs text-muted-foreground">{t('qa.evidence.version', { version: result.release.version })}</p>
    </div>
  );
}
