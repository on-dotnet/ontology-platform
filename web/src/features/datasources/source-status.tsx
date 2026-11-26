import { useTranslation } from 'react-i18next';

import { Badge, type BadgeTone } from '@/components/ui/badge';

import type { DataSource } from './api';

const tones = { archived: 'neutral', untested: 'neutral', ok: 'success', failed: 'error' } satisfies Record<string, BadgeTone>;

export function SourceStatus({ source }: { source: DataSource }) {
  const { t } = useTranslation();
  let status: keyof typeof tones = 'untested';
  if (source.status === 'archived') status = 'archived';
  else if (source.lastTest) status = source.lastTest.ok ? 'ok' : 'failed';
  return <Badge tone={tones[status]}>{t(`datasources.status.${status}`)}</Badge>;
}
