import { ChevronDown, ChevronRight } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { keyLabel } from '@/features/explore/object-values';

type Evidence = components['schemas']['QaEvidence'];

function EvidenceRows({ title, rows, elements }: { title: string; rows: Evidence['rows']; elements: Evidence['elements'] }) {
  const { t } = useTranslation();
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row.values)))];
  const labels = new Map(elements.map((element) => [element.id, element.label]));
  return (
    <section className="space-y-2">
      <h4 className="font-semibold">{title}</h4>
      {rows.length ? <div className="overflow-x-auto"><Table aria-label={title}>
        <TableHeader><TableRow>
          <TableHead>{t('explore.primaryKey')}</TableHead>
          {columns.map((id, index) => <TableHead key={id}>
            {labels.get(id) ?? t('qa.evidence.property', { number: index + 1 })}
          </TableHead>)}
        </TableRow></TableHeader>
        <TableBody>{rows.map((row) => <TableRow key={`${row.typeId}/${row.key}`}>
          <TableCell>{keyLabel(row)}</TableCell>
          {columns.map((id) => {
            const value = row.values[id];
            const display = typeof value === 'boolean' ? t(value ? 'explore.yes' : 'explore.no') : value;
            return <TableCell key={id} numeric={typeof value === 'number'}>
              {display ?? t('explore.noValue')}
              {row.truncated.includes(id) && <span className="ml-2 text-warning-strong">{t('explore.truncated')}</span>}
            </TableCell>;
          })}
        </TableRow>)}</TableBody>
      </Table></div> : <p>{t('explore.noMatches')}</p>}
    </section>
  );
}

export function AnswerEvidence({ evidence }: { evidence: Evidence }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  const Icon = open ? ChevronDown : ChevronRight;
  const documents = evidence.elements.flatMap((element) => element.documents);
  return (
    <div className="border-t border-border pt-3">
      <Button size="sm" variant="secondary" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Icon aria-hidden />{t('qa.evidence.title')}
      </Button>
      <div id={id} hidden={!open} className="mt-4 space-y-4">
        {!!evidence.elements.length && <section>
          <h4 className="font-semibold">{t('qa.evidence.elements')}</h4>
          <ul className="list-disc pl-5">{evidence.elements.map((element) => <li key={element.id}>
            <span>{element.label}</span>
            <span className="ml-2 text-muted-foreground">{t(element.kind === 'metric' ? 'metrics.kind' : `kinds.${element.kind}`)}</span>
            {element.iri && <span className="ml-2 break-all text-muted-foreground">{element.iri}</span>}
          </li>)}</ul>
        </section>}
        {!!evidence.bindings.length && <section>
          <h4 className="font-semibold">{t('qa.evidence.bindings')}</h4>
          <ul className="list-disc pl-5">{evidence.bindings.map((binding, index) => <li key={index}>
            <span>{binding.schema}.{binding.table}</span>
            <span className="ml-2 text-muted-foreground">{t('explore.primaryKey')}{t('common.colon')}</span>
            <span>{binding.keyColumns.join(t('common.listSeparator'))}</span>
          </li>)}</ul>
        </section>}
        {!!evidence.steps.length && <section>
          <h4 className="font-semibold">{t('qa.evidence.steps')}</h4>
          <ol className="list-decimal space-y-1 pl-5">{evidence.steps.map((step, index) => <li key={index}>
            <span>{step.typeLabel}</span>
            {step.conditions.map((condition, i) => <span key={i} className="ml-2">{condition}</span>)}
            <span className="ml-2 text-muted-foreground">{t('qa.evidence.stepCounts', { rows: step.rows, statements: step.statements })}</span>
            {step.truncated && <span className="ml-2 text-warning-strong">{t('explore.truncated')}</span>}
          </li>)}</ol>
        </section>}
        <EvidenceRows title={t('qa.evidence.rows')} rows={evidence.rows} elements={evidence.elements} />
        {!!evidence.tail.length && <EvidenceRows title={t('qa.evidence.tail')} rows={evidence.tail} elements={evidence.elements} />}
        {!!documents.length && <section>
          <h4 className="font-semibold">{t('qa.evidence.documents')}</h4>
          <ul className="space-y-2">{documents.map((doc, index) => <li key={index}>
            <a href={`/api/documents/${encodeURIComponent(doc.documentId)}/file`} className="text-primary-strong underline">{doc.documentName}</a>
            <span className="ml-2 text-muted-foreground">{t('qa.evidence.chunk', { number: doc.chunk })}</span>
            <blockquote className="border-l-2 border-border pl-3">{doc.quote}</blockquote>
          </li>)}</ul>
        </section>}
        <p className="text-muted-foreground">{t('qa.evidence.version', { version: evidence.release.version })}</p>
      </div>
    </div>
  );
}
