import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Badge } from '@/components/ui/badge';
import { RelativeTime } from '@/components/ui/relative-time';
import translations from '@/i18n';

type Row = components['schemas']['ObjectRow'];
type Property = components['schemas']['ObjectProperty'];

export function keyLabel(row: Row, { withColumns = false } = {}) {
  return row.source.key.map((part) => {
    const value = part.value.trim() ? part.value : translations.t('explore.blankValue');
    return withColumns ? `${part.column} = ${value}` : value;
  }).join(' · ') || translations.t('explore.blankValue');
}

export function PropertyValue({ property, row }: { property: Property; row: Row }) {
  const { t, i18n } = useTranslation();
  const value = row.values[property.propertyId];
  let display;
  if (value === null || value === undefined) display = t('explore.noValue');
  else if (typeof value === 'boolean') display = t(value ? 'explore.yes' : 'explore.no');
  else if ((property.datatype === 'date' || property.datatype === 'dateTime') && typeof value === 'string') {
    // A dateTime property can bind a date-only column. Calendar dates must keep their day in every timezone.
    if (/^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))) {
      display = <time dateTime={value}>{new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(value))}</time>;
    } else display = <RelativeTime value={value} />;
  } else display = String(value);
  return (
    <>
      {display}
      {row.truncated.includes(property.propertyId) && <Badge className="ml-2" tone="warning">{t('explore.truncated')}</Badge>}
    </>
  );
}
