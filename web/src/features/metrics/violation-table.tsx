import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { keyLabel } from '@/features/explore/object-values';

import { sampleLimit } from './api';

type Failure = components['schemas']['FailedCheck'];

function scalarText(t: TFunction, value: Failure['actual']) {
  if (value === null) return t('explore.noValue');
  if (typeof value === 'boolean') return t(value ? 'explore.yes' : 'explore.no');
  if (typeof value === 'string' && !value.trim()) return t('explore.blankValue');
  return String(value);
}

function requirement(t: TFunction, { check, expected }: Failure) {
  const value = Array.isArray(expected) ? expected.map((item) => scalarText(t, item)).join(t('rules.rangeSeparator')) : scalarText(t, expected);
  switch (check) {
    case 'minCount': return t('rules.countAtLeast', { n: value });
    case 'minLength': return t('rules.lengthAtLeast', { n: value });
    case 'maxLength': return t('rules.lengthAtMost', { n: value });
    case 'allowedValues': return t('metrics.allowedValues', { value });
    case 'pattern': return t('metrics.matchesPattern', { value });
    default: return t(`rules.${check}`, { value });
  }
}

export function ViolationTable({ rule, typeLabel }: { rule: components['schemas']['RuleResult']; typeLabel: string }) {
  const { t } = useTranslation();
  const samples = rule.samples.slice(0, sampleLimit);
  return (
    <div className="space-y-2 py-2">
      <Table aria-label={t('metrics.objects')}>
        <TableHeader><TableRow>
          <TableHead>{t('explore.primaryKey')}</TableHead><TableHead>{t('metrics.objectLabel')}</TableHead>
          <TableHead>{t('metrics.failedCheck')}</TableHead><TableHead numeric>{t('metrics.actual')}</TableHead>
        </TableRow></TableHeader>
        <TableBody>{samples.flatMap(({ object, failed }) => {
          const key = keyLabel(object);
          return failed.map((failure, index) => (
            <TableRow key={`${object.key}-${index}`}>
              {index === 0 && <>
                <TableCell rowSpan={failed.length}>{key}</TableCell>
                <TableCell rowSpan={failed.length}>{t('explore.detailTitle', { type: typeLabel, key })}</TableCell>
              </>}
              <TableCell>{requirement(t, failure)}</TableCell>
              <TableCell numeric>{scalarText(t, failure.actual)}</TableCell>
            </TableRow>
          ));
        })}</TableBody>
      </Table>
      {samples.length < rule.violations && <p className="text-sm text-muted-foreground">
        {t('metrics.partialSamples', { shown: samples.length, total: rule.violations })}
      </p>}
    </div>
  );
}
