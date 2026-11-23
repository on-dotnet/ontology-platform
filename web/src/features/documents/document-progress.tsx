import { CircleCheck, CircleX, Clock, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/cn';

import type { DocumentInfo } from './api';

/** Processing steps in order (`progress.step` values, spec 001 §4). */
export const PROCESS_STEPS = ['parse', 'terms', 'types', 'relations', 'changeset'] as const;
export type ProcessStep = (typeof PROCESS_STEPS)[number];
export type StepState = 'done' | 'active' | 'pending' | 'failed';

/** State of every step. A finished step that is not the last one means the next step is running. */
export function stepStates(document: Pick<DocumentInfo, 'status' | 'progress'>): StepState[] {
  const last = PROCESS_STEPS.length - 1;
  if (document.status === 'ready') return PROCESS_STEPS.map(() => 'done');
  if (document.status === 'queued') return PROCESS_STEPS.map(() => 'pending');
  const index = Math.max(0, (PROCESS_STEPS as readonly string[]).indexOf(document.progress.step));
  const finished = document.progress.total > 0 && document.progress.done >= document.progress.total;
  const current = finished && index < last ? index + 1 : index;
  const here: StepState = document.status === 'failed' ? 'failed' : 'active';
  return PROCESS_STEPS.map((_, step) => (step < current ? 'done' : step === current ? here : 'pending'));
}

const segmentClassName: Record<StepState, string> = {
  done: 'bg-success',
  active: 'bg-primary animate-pulse',
  pending: 'bg-border',
  failed: 'bg-error',
};

/** Step-level progress for one document: a label for the current state and one segment per step. */
export function DocumentProgress({ document }: { document: DocumentInfo }) {
  const { t } = useTranslation();
  const states = stepStates(document);
  const currentIndex = states.findIndex((state) => state === 'active' || state === 'failed');
  const currentStep = currentIndex >= 0 ? PROCESS_STEPS[currentIndex] : undefined;
  const { done, total } = document.progress;
  const showCount = currentStep !== undefined && currentStep === document.progress.step && total > 1 && done < total;

  let icon = <Clock className="size-4 text-muted-foreground" aria-hidden />;
  let label = t('documents.status.queued');
  if (document.status === 'ready') {
    icon = <CircleCheck className="size-4 text-success-strong" aria-hidden />;
    label = t('documents.status.ready');
  } else if (document.status === 'failed') {
    icon = <CircleX className="size-4 text-error-strong" aria-hidden />;
    label = currentStep ? t('documents.status.failedAt', { step: t(`documents.steps.${currentStep}`) }) : t('documents.status.failed');
  } else if (document.status !== 'queued' && currentStep) {
    icon = <LoaderCircle className="size-4 animate-spin text-primary-strong" aria-hidden />;
    label = t(`documents.steps.${currentStep}`);
  }

  return (
    <div className="min-w-48 max-w-64">
      <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        {icon}
        <span>{label}</span>
        {showCount ? <span className="tabular-nums text-muted-foreground">{t('documents.stepCount', { done, total })}</span> : null}
      </p>
      <ol className="mt-1.5 flex gap-1" aria-label={t('documents.stepsLabel')}>
        {PROCESS_STEPS.map((step, index) => {
          const state = states[index] ?? 'pending';
          return (
            <li key={step} className={cn('h-1.5 flex-1 rounded-full', segmentClassName[state])}>
              <span className="sr-only">
                {t(`documents.steps.${step}`)}
                {t('common.colon')}
                {t(`documents.stepStates.${state}`)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
