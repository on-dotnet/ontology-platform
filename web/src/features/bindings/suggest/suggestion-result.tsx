import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { Check, Circle, CircleDot } from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { bindingKeys } from '@/features/bindings/api';
import { ontologyKeys } from '@/features/ontologies/api';
import { changeSetKeys } from '@/features/review/api';
import { codeMessage, lookupText, useErrorMessage } from '@/i18n/error-message';

type Suggestion = components['schemas']['BindingSuggestion'];
const steps = ['catalog', 'match', 'columns', 'changeset'] as const satisfies readonly NonNullable<Suggestion['step']>[];

interface Props {
  initial: Suggestion;
  retryPending: boolean;
  onClose: () => void;
  onRetry: () => void;
}

export function SuggestionResult({ initial, retryPending, onClose, onRetry }: Props) {
  const { t, i18n } = useTranslation();
  const message = useErrorMessage();
  const client = useQueryClient();
  const poll = useQuery({
    queryKey: ['binding-suggestions', initial.id],
    queryFn: ({ signal }) => unwrap(api.GET('/api/binding-suggestions/{id}', { params: { path: { id: initial.id } }, signal })),
    initialData: initial,
    enabled: ({ state }) => {
      const { status } = state.data ?? initial;
      return !state.error && (status === 'queued' || status === 'running');
    },
    retry: false,
    refetchInterval: 2_000,
  });
  const { status, step, proposed, dropped, droppedReasons, changeSetId, errorCode, ontologyId } = poll.data;
  useEffect(() => {
    if (status !== 'succeeded' || !changeSetId) return;
    void client.invalidateQueries({ queryKey: bindingKeys.all });
    void client.invalidateQueries({ queryKey: changeSetKeys.list(ontologyId) });
    void client.invalidateQueries({ queryKey: ontologyKeys.list() });
    void client.invalidateQueries({ queryKey: ['workbench'] });
  }, [client, status, changeSetId, ontologyId]);

  if (poll.isError) {
    return (
      <InlineNotice tone="error" action={
        <Button variant="secondary" size="sm" loading={poll.isFetching} onClick={() => void poll.refetch()}>{t('common.retry')}</Button>
      }>{message(poll.error)}</InlineNotice>
    );
  }
  if (status === 'failed') {
    let reason = codeMessage(i18n, errorCode);
    if (errorCode === 'ai.not_configured' || errorCode === 'ai.unavailable' || errorCode === 'ai.invalid_output') {
      reason = t(`bindings.suggest.${errorCode}`);
    }
    return (
      <>
        <InlineNotice tone="error" title={t('bindings.suggest.failed')}>{reason}</InlineNotice>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t('bindings.suggest.manual')}</Button>
          <Button loading={retryPending} onClick={onRetry}>{t('common.retry')}</Button>
        </div>
      </>
    );
  }
  if (status === 'succeeded') {
    const otherKey = 'bindings.suggest.reasons.other';
    const reasons = new Map<string, number>();
    for (const [code, count] of Object.entries(droppedReasons ?? {})) {
      const reasonKey = `bindings.suggest.reasons.${code}`;
      const key = lookupText(i18n, reasonKey) ? reasonKey : otherKey;
      reasons.set(key, (reasons.get(key) ?? 0) + count);
    }
    // Most frequent first; ties by code so the order does not depend on jsonb key order. The
    // catch-all says the least, so it always comes last.
    const reasonRows = [...reasons].sort(([leftKey, leftCount], [rightKey, rightCount]) =>
      Number(leftKey === otherKey) - Number(rightKey === otherKey)
      || rightCount - leftCount
      || leftKey.localeCompare(rightKey));
    return (
      <>
        <div role="status" className="space-y-1">
          <p className="font-medium">{changeSetId ? t('bindings.suggest.proposed', { count: proposed }) : t('bindings.suggest.none')}</p>
          {dropped > 0 && (
            <div className="text-sm text-muted-foreground">
              <p>{t('bindings.suggest.dropped', { count: dropped })}</p>
              {reasonRows.length > 0 && (
                <ul className="list-disc ps-5">
                  {reasonRows.map(([key, count]) => (
                    <li key={key}>{t(key, { count })}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
        {changeSetId && (
          <div className="flex justify-end">
            <Link to="/review/$changeSetId" params={{ changeSetId }} className={buttonVariants()}>{t('bindings.pending.link')}</Link>
          </div>
        )}
      </>
    );
  }
  const index = step ? steps.indexOf(step) : -1;
  return (
    <div className="space-y-2">
      <p role="status" className={step ? 'sr-only' : 'text-sm text-muted-foreground'}>
        {step ? t('bindings.suggest.currentStep', { step: t(`bindings.suggest.steps.${step}`) }) : t('bindings.suggest.queued')}
      </p>
      <ol aria-label={t('bindings.suggest.progress')} className="space-y-2">
        {steps.map((item, i) => {
          const Icon = i === index ? CircleDot : i < index ? Check : Circle;
          return (
            <li key={item} aria-current={item === step ? 'step' : undefined}
              className="flex items-center gap-2 text-sm text-muted-foreground aria-[current=step]:font-semibold aria-[current=step]:text-primary-strong">
              <Icon aria-hidden className="size-4 shrink-0" />{t(`bindings.suggest.steps.${item}`)}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
