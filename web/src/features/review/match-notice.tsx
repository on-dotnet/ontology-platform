import { Combine, Split } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';

import { matchPlace, type ChangeItem, type ItemMatch, type MatchDecision } from './api';
import { AiSuggestionBadge } from './item-badges';

interface MatchNoticeProps {
  item: ChangeItem;
  match: ItemMatch;
  /** The change set the item belongs to: tells "another item of this change set" from one elsewhere. */
  changeSetId: string;
  /** "Merge" / "keep apart" are offered (reviewer role, change set still open). */
  canDecide: boolean;
  busy: boolean;
  onDecide: (decision: MatchDecision) => void;
}

/**
 * The item's alignment record (spec 004, 5.5): what it matches, the model's reason and the reviewer's
 * conclusion. It decides whether the merge creates the item or adds it to the other one, so it is shown
 * on the card (ui-guidelines §4), as a warning until someone has concluded.
 */
export function MatchNotice({ item, match, changeSetId, canDecide, busy, onDecide }: MatchNoticeProps) {
  const { t } = useTranslation();
  const target = t(`review.match.target.${matchPlace(match, changeSetId)}`, { label: match.label, title: match.changeSetTitle ?? '' });
  // Without a reason the record was not the model's call (same main name, or found by the lookup).
  const titleKey = match.kind === 'possible' ? 'review.match.possible' : match.reason ? 'review.match.same' : 'review.match.sameNoReason';
  const settled = match.decision !== null || match.keptApart || item.appliedElementId !== null;
  const conclusion =
    match.decision === 'same'
      ? t('review.match.decidedSame')
      : match.decision === 'different'
        ? t('review.match.decidedDifferent')
        : match.keptApart
          ? t('review.match.keptApart')
          : null;
  // Merging is for a possible duplicate; it would not take effect once the other side was kept apart.
  // A conclusion already given can always be pressed again to clear it.
  const offersMerge = (match.kind === 'possible' && !match.keptApart) || match.decision === 'same';
  const offersKeepApart = !match.keptApart || match.decision === 'different';
  const toggle = (decision: Exclude<MatchDecision, null>) => onDecide(match.decision === decision ? null : decision);

  const actions =
    canDecide && (offersMerge || offersKeepApart) ? (
      <div className="flex flex-wrap gap-2">
        {offersMerge ? (
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={match.decision === 'same'}
            disabled={busy}
            onClick={() => toggle('same')}
            className="aria-pressed:border-primary/50 aria-pressed:bg-primary-soft aria-pressed:text-primary-strong"
          >
            <Combine aria-hidden />
            {t('review.match.mergeInto')}
          </Button>
        ) : null}
        {offersKeepApart ? (
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={match.decision === 'different'}
            disabled={busy}
            onClick={() => toggle('different')}
            className="aria-pressed:border-primary/50 aria-pressed:bg-primary-soft aria-pressed:text-primary-strong"
          >
            <Split aria-hidden />
            {t('review.match.keepApart')}
          </Button>
        ) : null}
      </div>
    ) : null;

  return (
    <InlineNotice
      tone={settled ? 'info' : 'warning'}
      title={t(titleKey, { target })}
      announce={false}
      action={actions}
      className="mt-2 px-3 py-2"
    >
      {match.reason || conclusion ? (
        <div className="space-y-1">
          {match.reason ? (
            <p className="flex flex-wrap items-center gap-1.5">
              <AiSuggestionBadge />
              <span>{t('review.rationale', { text: match.reason })}</span>
            </p>
          ) : null}
          {conclusion ? <p>{conclusion}</p> : null}
        </div>
      ) : null}
    </InlineNotice>
  );
}
