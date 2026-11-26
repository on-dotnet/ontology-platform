import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { AiSuggestionBadge } from '@/features/review/item-badges';

import type { Question } from './api';
import { AnswerEvidence } from './answer-evidence';

const notices = {
  rows_not_shared: 'qa.rowsNotShared', answer_unavailable: 'qa.answerUnavailable',
  cited_unknown: 'qa.citedUnknown', rows_truncated: 'qa.rowsTruncated',
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-1"><h3 className="font-semibold">{title}</h3>{children}</section>;
}

export function AnswerCard({ question }: { question: Question }) {
  const { t } = useTranslation();
  const { answer, evidence, plan } = question;
  if (!answer) return null;
  const { facts } = answer;
  const notes = new Set(answer.notes);
  if (evidence?.truncated) notes.add('rows_truncated');
  const hasFacts = facts.count !== null || facts.metric || facts.violations !== null || facts.objects.length > 0;
  return (
    <div className="space-y-4 text-sm">
      {answer.text && <Section title={t('qa.conclusion')}>
        <AiSuggestionBadge />
        <p className="whitespace-pre-wrap">{answer.text}</p>
      </Section>}
      {hasFacts && <Section title={t('qa.facts')}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          {facts.count !== null && <><dt>{t('metrics.matched')}</dt><dd>{facts.count}</dd></>}
          {facts.metric && <><dt>{facts.metric.label}</dt><dd>{facts.metric.display ?? t('explore.noValue')}</dd></>}
          {facts.violations !== null && <><dt>{t('metrics.violations')}</dt><dd>{facts.violations}</dd></>}
        </dl>
        {!!facts.objects.length && <ul className="list-disc pl-5">
          {facts.objects.map((object) => <li key={`${object.typeId}/${object.key}`}>{object.label}</li>)}
        </ul>}
      </Section>}
      {!!plan?.assumptions.length && <Section title={t('qa.assumptions')}>
        <ul className="list-disc pl-5">{plan.assumptions.map((text, index) => <li key={index}>{text}</li>)}</ul>
      </Section>}
      {!!answer.counterpoints.length && <Section title={t('qa.counterpoints')}>
        <ul className="list-disc pl-5">{answer.counterpoints.map((text, index) => <li key={index}>{text}</li>)}</ul>
      </Section>}
      {[...notes].map((note) => <InlineNotice key={note} tone="info" title={t(notices[note])} />)}
      {evidence && <AnswerEvidence evidence={evidence} />}
    </div>
  );
}
