import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { Button, buttonVariants } from '@/components/ui/button';
import { usePermissions } from '@/features/auth/permissions';

import { isGapActive, useGapProposal, type GapPolling, type Question } from './api';
import { QuestionError } from './question-error';

const linkClass = buttonVariants({ variant: 'secondary', size: 'sm' });

type GapActionProps = { question: Question; gapPolling: GapPolling };

function SemanticProposal({ question, gapPolling }: GapActionProps) {
  const { t } = useTranslation();
  const { pending, error, submit } = useGapProposal(question.id, gapPolling);
  const proposal = question.gapProposal;
  if (!proposal || isGapActive(proposal)) {
    const stale = !!proposal && gapPolling.stale;
    const busy = pending || (!!proposal && !stale);
    return <div className="space-y-2">
      {stale && <p role="status">{t('qa.proposalStale')}</p>}
      <Button size="sm" loading={busy} onClick={submit}>{t(stale ? 'qa.retry' : busy ? 'qa.proposing' : 'qa.propose')}</Button>
      {(!proposal || stale) && error && <QuestionError error={error} />}
    </div>;
  }
  if (proposal.status === 'failed') return <QuestionError error={proposal.errorCode} />;
  if (proposal.status === 'empty') return <p>{t('qa.gapEmpty')}</p>;
  return <div className="space-y-1">
    <div className="flex flex-wrap items-center gap-2">
      <span>{t('qa.proposalReady')}</span>
      {proposal.changeSetId && <Link to="/review/$changeSetId" params={{ changeSetId: proposal.changeSetId }} className={linkClass}>
        {t('assistant.result.review')}
      </Link>}
    </div>
    {proposal.dropped > 0 && <p>{t('qa.proposalDropped', { count: proposal.dropped })}</p>}
  </div>;
}

export function GapActions({ question, gapPolling }: GapActionProps) {
  const { t } = useTranslation();
  const { canEditBindings } = usePermissions();
  const { gaps, ontologyId } = question;
  if (!canEditBindings || !gaps) return null;
  return <div className="flex flex-wrap items-center gap-2">
    {gaps.elements.some((element) => element.kind !== 'metric') && <SemanticProposal key={question.id} question={question} gapPolling={gapPolling} />}
    {gaps.elements.some((element) => element.kind === 'metric') && (
      <Link to="/ontology" search={{ ontology: ontologyId, view: 'list' }} className={linkClass}>{t('metrics.create')}</Link>
    )}
    {gaps.bindings.length > 0 && <Link to="/data" className={linkClass}
      search={() => ({ ontologyId, typeIds: gaps.bindings.map((binding) => binding.typeId).join(',') })}>
      {t('qa.suggestBindings')}
    </Link>}
  </div>;
}
