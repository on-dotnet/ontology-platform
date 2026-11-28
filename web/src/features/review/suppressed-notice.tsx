import { Link } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import type { components } from '@/api/schema';

type SuppressedItem = components['schemas']['SuppressedItem'];

export function SuppressedNotice({ items, total, ontologyId }: { items: SuppressedItem[]; total: number; ontologyId: string }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <InlineNotice tone="info" className="mb-4" title={t('review.suppressed.title', { count: total })}
      action={<Button variant="ghost" size="sm" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {t(open ? 'review.suppressed.hide' : 'review.suppressed.show')}
      </Button>}>
      {open ? <ul className="mt-2 space-y-2">
        {items.map((item, index) => {
          const name = (i18n.resolvedLanguage ?? i18n.language).startsWith('zh') ? item.labelZh ?? item.labelEn : item.labelEn ?? item.labelZh;
          const q = item.cause === 'depends_on_suppressed' ? item.dependsOn : name;
          return <li key={`${item.memoryEntryId ?? item.kind}-${index}`}>
            <Link to="/review/memory" search={{ ontology: ontologyId, ...(item.memoryEntryId ? {
              ...(q ? { q } : {}),
              entry: item.memoryEntryId,
            } : {}) }}
              className="rounded text-info-strong hover:underline">
              {name ?? t('review.unknownItem')}
            </Link>
            <span className="ml-2 text-muted-foreground">{t(`kinds.${item.kind}`)} · {item.cause === 'memory'
              ? t('review.suppressed.memory') : t('review.suppressed.dependsOn', { name: item.dependsOn ?? t('review.unknownType') })}</span>
          </li>;
        })}
        {total > items.length ? <li className="text-muted-foreground">{t('review.suppressed.more', { count: total - items.length })}</li> : null}
      </ul> : null}
    </InlineNotice>
  );
}
