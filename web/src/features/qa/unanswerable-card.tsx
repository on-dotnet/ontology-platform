import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';

import type { Question } from './api';

export function UnanswerableCard({ gaps, actions }: { gaps: Question['gaps']; actions?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <InlineNotice tone="warning" title={t('qa.unanswerable')} action={actions}>
      <div className="space-y-3">
        {!!gaps?.elements.length && <section>
          <h3 className="font-semibold">{t('qa.missingElements')}</h3>
          <ul className="list-disc space-y-1 pl-5">
            {gaps.elements.map((element, index) => <li key={index}>
              <span className="font-medium">{element.labelZh}</span>
              <p>{element.description}</p>
            </li>)}
          </ul>
        </section>}
        {!!gaps?.bindings.length && <section>
          <h3 className="font-semibold">{t('qa.missingBindings')}</h3>
          <ul className="list-disc pl-5">
            {gaps.bindings.map((binding) => <li key={binding.typeId}>{binding.label}</li>)}
          </ul>
        </section>}
      </div>
    </InlineNotice>
  );
}
