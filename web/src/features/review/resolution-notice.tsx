import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';

import type { ChangeItem, ItemResolution } from './api';
import { effectiveFields } from './item-fields';

interface ResolutionNoticeProps {
  item: ChangeItem;
  resolution: ItemResolution;
}

/**
 * What a merge does with an item other than adding it as proposed (spec 004, 5.4): it goes into an
 * existing element, gets another local name, or only adds what the element lacks. These change the
 * result, so they are shown on the card (ui-guidelines §4), as a warning before the merge and as a
 * plain note after it.
 */
export function ResolutionNotice({ item, resolution }: ResolutionNoticeProps) {
  const { t } = useTranslation();
  const merged = item.appliedElementId !== null;
  const name = resolution.elementLabel ?? t('review.unknownElement');
  const kept = resolution.keptFields.map((field) => t(`review.fields.${field}`)).join(t('common.listSeparator'));
  const keptNote = kept ? t('review.resolution.kept', { fields: kept }) : null;
  // Only an object type has relations and properties that refer to it.
  const intoKey = item.kind === 'entity_type' ? 'review.resolution.intoDescription' : 'review.resolution.intoMemberDescription';

  if (resolution.mode === 'into') {
    return merged ? (
      <Notice merged title={t('review.resolution.intoDone', { name })} />
    ) : (
      <Notice title={t('review.resolution.into', { name })}>
        <p>{t(intoKey, { name })}</p>
        {keptNote ? <p>{keptNote}</p> : null}
      </Notice>
    );
  }
  if (resolution.mode === 'rename') {
    const localName = resolution.localName ?? '';
    return merged ? (
      <Notice merged title={t('review.resolution.renameDone', { localName })} />
    ) : (
      <Notice title={t('review.resolution.rename', { wanted: effectiveFields(item).localName ?? '' })}>
        {t('review.resolution.renameDescription', { localName })}
      </Notice>
    );
  }
  if (resolution.mode === 'update' && !merged) {
    if (item.op === 'restore') {
      return (
        <Notice title={t('review.resolution.restored', { name })}>
          <p>{t('review.resolution.restoredDescription')}</p>
          {keptNote ? <p>{keptNote}</p> : null}
        </Notice>
      );
    }
    return keptNote ? <Notice title={keptNote} /> : null;
  }
  return null;
}

function Notice({ title, merged = false, children }: { title: string; merged?: boolean; children?: ReactNode }) {
  return (
    <InlineNotice tone={merged ? 'info' : 'warning'} title={title} announce={false} className="mt-2 px-3 py-2">
      {children}
    </InlineNotice>
  );
}
