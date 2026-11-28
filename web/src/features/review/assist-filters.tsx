import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { NativeSelect } from '@/components/ui/native-select';

import type { ReviewAssist } from './api';

export type AssistFilter = 'risk' | 'reject' | 'edit' | null;

export function AssistFilters({ assist, filter, group, onFilter, onGroup }: {
  assist: ReviewAssist; filter: AssistFilter; group: string; onFilter: (filter: AssistFilter) => void; onGroup: (group: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t('reviewAssist.filters')} className="flex flex-wrap items-center gap-2">
      {(['risk', 'reject', 'edit'] as const).map((value) => (
        <Button key={value} variant="secondary" size="sm" aria-pressed={filter === value}
          className="aria-pressed:bg-info-soft aria-pressed:text-info-strong"
          onClick={() => onFilter(filter === value ? null : value)}>{t(`reviewAssist.filter.${value}`)}</Button>
      ))}
      <NativeSelect aria-label={t('reviewAssist.group')} value={group} onChange={(event) => onGroup(event.target.value)}>
        <option value="">{t('reviewAssist.allGroups')}</option>
        {assist.groups.map((entry, index) => <option key={index} value={String(index)}>{t('reviewAssist.groupOption', { title: entry.title, count: entry.itemIds.length })}</option>)}
      </NativeSelect>
    </div>
  );
}
