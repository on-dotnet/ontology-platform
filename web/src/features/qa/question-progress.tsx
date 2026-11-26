import { CheckCircle2, Circle, CircleDot } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';

import type { Question } from './api';

const stages = ['plan', 'query', 'answer'] as const;
const position = { plan: 0, check: 0, query: 1, answer: 2, done: 3 };

export function QuestionProgress({ question }: { question: Question }) {
  const { t } = useTranslation();
  const queued = question.status === 'queued';
  const current = queued ? -1 : position[question.step ?? 'plan'];
  return (
    <div role="status" className="space-y-3">
      <Badge tone={queued ? 'neutral' : 'info'}>{t(queued ? 'qa.queued' : 'assistant.progress.running')}</Badge>
      <ol aria-label={t('assistant.progress.label')} className="flex flex-wrap gap-4">
        {stages.map((stage, index) => {
          const active = index === current;
          const done = index < current;
          const Icon = done ? CheckCircle2 : active ? CircleDot : Circle;
          return <li key={stage} aria-current={active ? 'step' : undefined}
            className={done ? 'text-success-strong' : active ? 'text-primary-strong' : 'text-muted-foreground'}>
            <Icon className="mr-1 inline size-4" aria-hidden /><span>{t(`qa.progress.${stage}`)}</span>
            <span className="sr-only">{t('common.colon')}{t(`assistant.stepStates.${done ? 'done' : active ? 'active' : 'pending'}`)}</span>
          </li>;
        })}
      </ol>
    </div>
  );
}
