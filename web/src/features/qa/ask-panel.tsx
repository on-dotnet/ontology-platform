import { Link } from '@tanstack/react-router';
import { History, MessageCircleQuestion } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError, isForbidden } from '@/api/errors';
import { EmptyState } from '@/components/states/empty-state';
import { ForbiddenState } from '@/components/states/forbidden-state';
import { LoadingState } from '@/components/states/loading-state';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { aiHealth, useAiStatus } from '@/features/ai/api';

import { AnswerCard } from './answer-card';
import { isActive, useCreateQuestion, useQuestion, useRecentQuestions } from './api';
import { GapActions } from './gap-actions';
import { QuestionError } from './question-error';
import { QuestionForm } from './question-form';
import { QuestionProgress } from './question-progress';
import { RecentQuestions } from './recent-questions';
import { UnanswerableCard } from './unanswerable-card';

export function AskPanel({ ontologyId }: { ontologyId: string }) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [selection, select] = useState<string>();
  const recent = useRecentQuestions(ontologyId);
  const items = recent.data?.items ?? [];
  const id = selection ?? items[0]?.id;
  const detail = useQuestion(id, items.find((item) => item.id === id));
  const question = detail.data;
  const create = useCreateQuestion(ontologyId, select);
  const ai = useAiStatus();
  const errors = [recent.error, detail.error, create.error];
  if (errors.some(isForbidden)) return <ForbiddenState requiredRole="viewer" />;
  const hasError = (code: string) => errors.some((error) => isApiError(error) && error.code === code);
  if (hasError('query.no_release')) return <Card>
    <EmptyState icon={History} title={t('qa.errors.query.no_release')} action={
      <Link to="/releases" search={{ ontology: ontologyId }} className={buttonVariants()}>{t('qa.publish')}</Link>
    } />
  </Card>;

  const unconfigured = hasError('ai.not_configured') || (!!ai.data && aiHealth(ai.data) === 'not_configured');
  return (
    <div className="grid items-start gap-6 lg:grid-cols-4">
      <div className="min-w-0 space-y-6">
        <QuestionForm text={text} setText={setText} sending={create.isPending} unconfigured={unconfigured}
          error={create.error} onSubmit={(question) => create.mutate({ question }, {
            onSuccess: () => setText((draft) => draft.trim() === question ? '' : draft),
          })} />
        <RecentQuestions items={items} selectedId={id} selected={question} disabled={unconfigured}
          onSelect={select} onExample={setText} state={recent.error
            ? <QuestionError error={recent.error} retry={() => void recent.refetch()} />
            : recent.isPending ? <LoadingState /> : undefined} />
      </div>
      <Card className="min-w-0 space-y-4 break-words p-5 lg:col-span-3">
        {detail.error ? <QuestionError error={detail.error} retry={() => void detail.refetch()} />
          : question ? <>
            <CardTitle>{question.question}</CardTitle>
            {isActive(question) && <QuestionProgress question={question} />}
            {question.status === 'answered' && <AnswerCard key={question.id} question={question} />}
            {question.status === 'unanswerable' && <UnanswerableCard gaps={question.gaps} actions={<div className="space-y-2">
              <GapActions question={question} />
              <Button variant="secondary" size="sm" disabled={unconfigured || create.isPending}
                onClick={() => create.mutate({ question: question.question })}>{t('qa.askAgain')}</Button>
            </div>} />}
            {question.status === 'failed' && <QuestionError error={question.errorCode}
              disabled={unconfigured || create.isPending} retry={() => create.mutate({ question: question.question })} />}
          </> : id || recent.isPending ? <LoadingState variant="detail" />
            : <EmptyState icon={MessageCircleQuestion} title={t('qa.selectQuestion')} />}
      </Card>
    </div>
  );
}
