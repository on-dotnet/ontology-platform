import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';

import type { AssistItem as AssistItemData, AssistRisk } from './api';

const DETAILS = new Set(['evidence_not_found', 'no_evidence', 'low_confidence', 'possible_duplicate', 'undecided_match', 'kept_fields', 'stale_target', 'local_name_style', 'missing_label_en', 'similar_to_rejected']);

export function AssistItem({ item, canEdit, onApplyRename }: { item: AssistItemData; canEdit: boolean; onApplyRename: () => void }) {
  const { t } = useTranslation();
  const riskText = (risk: AssistRisk) => risk.reason || t(`reviewAssist.detail.${risk.detail && DETAILS.has(risk.detail) ? risk.detail : 'other'}`);
  return (
    <div className="mt-2 space-y-2">
      {item.risks.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {item.risks.map((risk, index) => {
            const isAi = risk.source === 'ai';
            const label = t(`reviewAssist.risk.${risk.code}`);
            const detail = riskText(risk);
            return (
              <Tooltip key={index} content={detail}>
                <button type="button" className="rounded-md focus-visible:outline-2 focus-visible:outline-ring"
                  aria-label={t(isAi ? 'reviewAssist.aiRiskLabel' : 'reviewAssist.riskLabel', { label, detail })}>
                  <Badge tone={isAi ? 'info' : 'warning'}>{isAi ? t('reviewAssist.aiRisk', { label }) : label}</Badge>
                </button>
              </Tooltip>
            );
          })}
        </div>
      ) : null}
      {item.suggestion ? <p className={cn('text-sm', item.stale ? 'text-muted-foreground' : 'text-info-strong')}>
        {t(item.reason ? 'reviewAssist.suggestionWithReason' : 'reviewAssist.suggestion', {
          kind: t(`reviewAssist.suggestions.${item.suggestion}`), reason: item.reason,
        })}
        {item.stale ? <span className="ml-2">{t('reviewAssist.staleItem')}</span> : null}
      </p> : null}
      {canEdit && !item.stale && item.suggestion === 'edit' && item.rename ? (
        <Button variant="secondary" size="sm" onClick={onApplyRename}>{t('reviewAssist.applyRename')}</Button>
      ) : null}
    </div>
  );
}
