import { Link } from '@tanstack/react-router';
import { ChevronRight, CircleAlert, CircleCheck, Circle, LoaderCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { useChangeSet, type ChangeOp } from '@/features/review/api';
import { AiSuggestionBadge } from '@/features/review/item-badges';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

import { ASSISTANT_STEPS, isActive, stopsPolling, useAssistantRequest, type AssistantRequest } from './api';

export type StepState = 'done' | 'active' | 'pending';

/** State of every pipeline step: the reported step is running, the ones before it are done. */
export function stepStates(request: Pick<AssistantRequest, 'status' | 'step'>): StepState[] {
  if (request.status === 'succeeded') return ASSISTANT_STEPS.map(() => 'done');
  if (request.status === 'queued') return ASSISTANT_STEPS.map(() => 'pending');
  const current = Math.max(0, request.step ? ASSISTANT_STEPS.indexOf(request.step) : 0);
  return ASSISTANT_STEPS.map((_, index) => (index < current ? 'done' : index === current ? 'active' : 'pending'));
}

const stepIcon: Record<StepState, typeof Circle> = { done: CircleCheck, active: LoaderCircle, pending: Circle };
const stepIconClassName: Record<StepState, string> = {
  done: 'text-success-strong',
  active: 'animate-spin text-primary-strong',
  pending: 'text-muted-foreground',
};

/**
 * "读取本体 → 调用模型 → 生成变更集" with the current step marked; no log (ui-guidelines §7). Not a live
 * region: the panel announces once when the request ends.
 */
function StepProgress({ request }: { request: AssistantRequest }) {
  const { t } = useTranslation();
  const states = stepStates(request);
  return (
    <div className="rounded-lg border border-border px-3 py-2.5">
      <p className="text-xs font-semibold text-muted-foreground">
        {t(request.status === 'queued' ? 'assistant.progress.queued' : 'assistant.progress.running')}
      </p>
      <ol aria-label={t('assistant.progress.label')} className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs">
        {ASSISTANT_STEPS.map((step, index) => {
          const state = states[index] ?? 'pending';
          const Icon = stepIcon[state];
          return (
            <li key={step} className="flex items-center gap-1.5">
              {index > 0 ? <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden /> : null}
              <Icon className={cn('size-3.5 shrink-0', stepIconClassName[state])} aria-hidden />
              <span className={state === 'active' ? 'font-semibold text-foreground' : 'text-muted-foreground'}>
                {t(`assistant.steps.${step}`)}
              </span>
              <span className="sr-only">
                {t('common.colon')}
                {t(`assistant.stepStates.${state}`)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const OPS: readonly ChangeOp[] = ['create', 'update', 'delete', 'restore'];

/** How many items the change set creates, updates, deletes and restores, and the way to review it. */
function ChangeSummary({ changeSetId }: { changeSetId: string }) {
  const { t } = useTranslation();
  const query = useChangeSet(changeSetId);

  let summary;
  if (query.isPending) {
    summary = (
      <div role="status">
        <span className="sr-only">{t('common.loading')}</span>
        <Skeleton className="h-4 w-40" />
      </div>
    );
  } else if (query.isError) {
    summary = <span className="text-muted-foreground">{t('assistant.result.summaryFailed')}</span>;
  } else {
    const { items } = query.data;
    const parts = OPS.map((op) => ({ op, count: items.filter((item) => item.op === op).length }))
      .filter((part) => part.count > 0)
      .map((part) => t('assistant.result.opCount', { op: t(`review.op.${part.op}`), count: part.count }));
    summary = t('assistant.result.summary', { count: items.length, ops: parts.join(t('common.listSeparator')) });
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
      <div className="min-w-0 flex-1 text-sm text-foreground">{summary}</div>
      <Link to="/review/$changeSetId" params={{ changeSetId }} className={buttonVariants({ variant: 'soft', size: 'sm' })}>
        {t('assistant.result.review')}
      </Link>
    </div>
  );
}

/** The assistant's answer: its reply, what it could not do, and the change set it proposes. */
function ResultCard({ request }: { request: AssistantRequest }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2.5 rounded-lg border border-info/25 bg-card p-3">
      <AiSuggestionBadge />
      {request.reply ? <p className="whitespace-pre-wrap break-words text-sm text-foreground">{request.reply}</p> : null}
      {request.dropped > 0 ? (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <CircleAlert className="mt-px size-3.5 shrink-0 text-warning-strong" aria-hidden />
          <span>{t('assistant.result.dropped', { count: request.dropped })}</span>
        </p>
      ) : null}
      {request.changeSetId ? (
        <ChangeSummary changeSetId={request.changeSetId} />
      ) : (
        <p className="border-t border-border pt-2.5 text-xs text-muted-foreground">{t('assistant.result.noChanges')}</p>
      )}
    </div>
  );
}

const FAILURE_REASONS = ['not_configured', 'unavailable', 'invalid_output'] as const;
type FailureReason = (typeof FAILURE_REASONS)[number] | 'other';

/** Gateway failures have their own advice (configure vs. wait); anything else is generic. */
export function failureReason(errorCode: string | null): FailureReason {
  const code = errorCode?.startsWith('ai.') ? errorCode.slice(3) : undefined;
  return FAILURE_REASONS.find((reason) => reason === code) ?? 'other';
}

interface RequestEntryProps {
  request: AssistantRequest;
  /** Offered on failures when the user may ask the assistant. */
  onRetry?: (() => void) | undefined;
  retrying?: boolean;
  /** Why sending this request again failed, shown with it. */
  retryError?: unknown;
  /** Called when a request seen in progress ends (or can no longer be followed). */
  onSettled?: ((outcome: 'succeeded' | 'failed' | 'lost') => void) | undefined;
}

/** One request: the user's words, then the progress, the result or the failure. */
export function RequestEntry({ request, onRetry, retrying = false, retryError, onSettled }: RequestEntryProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const polled = useAssistantRequest(request, (next) => onSettled?.(next.status === 'succeeded' ? 'succeeded' : 'failed'), () =>
    onSettled?.('lost'),
  );
  // The list holds the outcome once known; until then the polled copy is the newer one.
  const shown = isActive(request) ? polled.data : request;
  const reason = failureReason(shown.errorCode);
  // Polling stopped for good (e.g. the request is gone): say so instead of spinning on.
  const lost = isActive(shown) && polled.isError && stopsPolling(polled.error);

  let outcome;
  if (lost) {
    outcome = (
      <InlineNotice tone="error" announce={false} title={t('assistant.lostTitle')}>
        {message(polled.error)}
      </InlineNotice>
    );
  } else if (isActive(shown)) {
    outcome = <StepProgress request={shown} />;
  } else if (shown.status === 'failed') {
    outcome = (
      <div className="space-y-2">
        {/* Past failures are part of the history: not read out when the list appears. */}
        <InlineNotice
          tone="error"
          announce={false}
          title={t(`assistant.failure.${reason}.title`)}
          action={
            onRetry ? (
              <Button variant="secondary" size="sm" loading={retrying} onClick={onRetry}>
                {retrying ? null : <RefreshCw aria-hidden />}
                {t('common.retry')}
              </Button>
            ) : undefined
          }
        >
          {t(`assistant.failure.${reason}.description`)}
        </InlineNotice>
        {retryError ? (
          <InlineNotice tone="error" title={t('assistant.retryFailedTitle')}>
            {message(retryError)}
          </InlineNotice>
        ) : null}
      </div>
    );
  } else {
    outcome = <ResultCard request={shown} />;
  }

  return (
    <li className="space-y-2">
      <div className="ml-8 rounded-lg bg-muted px-3 py-2">
        <p className="whitespace-pre-wrap break-words text-sm text-foreground">
          <span className="sr-only">{t('assistant.youAsked')}</span>
          {shown.message}
        </p>
        <RelativeTime value={shown.createdAt} className="mt-0.5 block text-xs text-muted-foreground" />
      </div>
      {outcome}
    </li>
  );
}
