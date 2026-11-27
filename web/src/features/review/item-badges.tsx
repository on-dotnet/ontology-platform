import { Check, FilePlus, PenLine, RotateCcw, Sparkles, Trash2, X, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { WarnTip } from '@/components/feedback/hint-tip';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Tooltip } from '@/components/ui/tooltip';
import { formatPercent } from '@/lib/format';

import { confidenceTier, type ChangeOp, type ConfidenceTier, type Decision, type ItemFlag, type RejectReason } from './api';

export function RejectReasonBadge({ reason }: { reason: RejectReason }) {
  const { t } = useTranslation();
  return <Badge tone="neutral">{t(`review.rejectReasons.${reason}`)}</Badge>;
}

/** "✦ AI 建议" in the AI color (ui-guidelines §7). */
export function AiSuggestionBadge() {
  const { t } = useTranslation();
  return (
    <Badge tone="info">
      <Sparkles aria-hidden />
      {t('review.aiSuggestion')}
    </Badge>
  );
}

const tierTone: Record<ConfidenceTier, BadgeTone> = { high: 'success', medium: 'warning', low: 'error' };

/** High / medium / low; the exact percentage on hover and for screen readers. */
export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const { t, i18n } = useTranslation();
  const tier = confidenceTier(confidence);
  const percent = formatPercent(confidence, i18n.resolvedLanguage ?? i18n.language);
  return (
    <Tooltip content={t('review.confidencePercent', { percent })}>
      <Badge tone={tierTone[tier]}>
        {t(`review.confidence.${tier}`)}
        <span className="sr-only">{t('review.confidencePercentShort', { percent })}</span>
      </Badge>
    </Tooltip>
  );
}

/** One "!" per flag, explaining what to check before deciding. */
export function FlagTips({ flags }: { flags: readonly ItemFlag[] }) {
  const { t } = useTranslation();
  return (
    <>
      {flags.map((flag) => (
        <WarnTip key={flag} label={t(`review.flags.${flag}.label`)}>
          {t(`review.flags.${flag}.description`)}
        </WarnTip>
      ))}
    </>
  );
}

const decisionTone: Record<Decision, BadgeTone> = { pending: 'neutral', accepted: 'success', rejected: 'error' };

export function DecisionBadge({ decision }: { decision: Decision }) {
  const { t } = useTranslation();
  return (
    <Badge tone={decisionTone[decision]}>
      {decision === 'accepted' ? <Check aria-hidden /> : null}
      {decision === 'rejected' ? <X aria-hidden /> : null}
      {t(`review.decision.${decision}`)}
    </Badge>
  );
}

const opStyle: Record<ChangeOp, { tone: BadgeTone; icon: LucideIcon }> = {
  create: { tone: 'primary', icon: FilePlus },
  update: { tone: 'secondary', icon: PenLine },
  delete: { tone: 'error', icon: Trash2 },
  restore: { tone: 'success', icon: RotateCcw },
};

/** What a change item does to the ontology; delete and restore stand out in color and icon. */
export function OpBadge({ op }: { op: ChangeOp }) {
  const { t } = useTranslation();
  const { tone, icon: Icon } = opStyle[op];
  return (
    <Badge tone={tone}>
      <Icon aria-hidden />
      {t(`review.op.${op}`)}
    </Badge>
  );
}
