import { Boxes } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { EmptyState } from '@/components/states/empty-state';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { currentLocale } from '@/i18n';
import { usePagination } from '@/lib/pagination';

import { useRuleReport } from './api';
import { ReadResult } from './read-result';
import { RuleTable } from './rule-table';

interface Props {
  id: string;
  releaseId: string;
  types: components['schemas']['ObjectTypeInfo'][];
}

export function RuleCheck({ id, releaseId, types }: Props) {
  const { t } = useTranslation();
  const selectId = useId();
  const [selected, setSelected] = useState('');
  const [checkedType, setCheckedType] = useState('');
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const type = types.find((item) => item.typeId === selected && !item.problem) ?? types.find((item) => !item.problem);
  const requested = !!type && checkedType === type.typeId;
  const query = useRuleReport(id, releaseId, type?.typeId ?? '', currentLocale(), requested);
  const page = usePagination(query.data?.results.length ?? 0, type?.typeId);
  const toggle = (key: string) => setExpanded((previous) => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });
  if (!type) return <EmptyState icon={Boxes} headingLevel="h3" title={t(types.length ? 'explore.noAvailableTypes' : 'explore.noBindings')} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 space-y-1">
          <Label htmlFor={selectId}>{t('metrics.chooseType')}</Label>
          <NativeSelect id={selectId} value={type.typeId} onChange={(event) => {
            setSelected(event.target.value);
            setCheckedType('');
          }}>
            {types.map((item) => <option key={item.typeId} value={item.typeId} disabled={!!item.problem}>{item.label}</option>)}
          </NativeSelect>
        </div>
        <Button loading={query.isFetching} onClick={() => {
          if (requested) void query.refetch();
          else {
            setSelected(type.typeId);
            setCheckedType(type.typeId);
            setExpanded(new Set());
          }
        }}>{t('metrics.check')}</Button>
      </div>
      {requested && <ReadResult query={query} onRestart={query.retryWithCatalog}>
        {(report) => <>
          <p className="text-sm tabular-nums text-muted-foreground">
            {t('metrics.checkSummary', { checked: report.checkedRules, unchecked: report.uncheckedRules })}
          </p>
          <RuleTable results={report.results} typeLabel={type.label} page={page} expanded={expanded} onToggle={toggle} />
        </>}
      </ReadResult>}
    </div>
  );
}
