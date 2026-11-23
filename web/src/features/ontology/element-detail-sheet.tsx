import type { UseQueryResult } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, ChevronDown, GitMerge } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogDescription, DialogTitle, SheetContent } from '@/components/ui/dialog';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { EvidenceExcerpt } from '@/features/documents/evidence-excerpt';
import {
  elementLabel,
  useElementDetail,
  useElements,
  type Element,
  type ElementDetail,
  type Evidence,
} from '@/features/ontologies/api';
import { cn } from '@/lib/cn';

import { kindTone } from './element-list';

interface ElementDetailSheetProps {
  ontologyId: string;
  /** The element shown; the sheet is closed when null. */
  elementId: string | null;
  onSelect: (elementId: string) => void;
  onClose: () => void;
}

/** Side panel with an element's definition, synonyms, properties and relations, and its source evidence. */
export function ElementDetailSheet({ ontologyId, elementId, onSelect, onClose }: ElementDetailSheetProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={elementId !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" closeLabel={t('common.close')} className="w-[min(32rem,100vw)] max-w-full overflow-y-auto">
        {elementId ? <ElementDetailBody key={elementId} ontologyId={ontologyId} elementId={elementId} onSelect={onSelect} /> : null}
      </SheetContent>
    </Dialog>
  );
}

function ElementDetailBody({ ontologyId, elementId, onSelect }: { ontologyId: string; elementId: string; onSelect: (id: string) => void }) {
  const { t } = useTranslation();
  const detail = useElementDetail(ontologyId, elementId);
  const all = useElements(ontologyId);
  return (
    <div className="p-6 pr-12">
      <QueryState
        query={detail}
        loading={
          <div className="space-y-3" role="status" aria-busy>
            <DialogTitle className="sr-only">{t('common.loading')}</DialogTitle>
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-32 rounded-xl" />
          </div>
        }
      >
        {(element) => <ElementDetailContent element={element} related={all} onSelect={onSelect} />}
      </QueryState>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2 border-t border-border pt-4">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  );
}

function ElementLink({ element, onSelect, language }: { element: Element | undefined; onSelect: (id: string) => void; language: string }) {
  const { t } = useTranslation();
  if (!element) return <span className="text-muted-foreground">{t('review.unknownType')}</span>;
  return (
    <button type="button" onClick={() => onSelect(element.id)} className="rounded font-medium text-primary-strong hover:underline">
      {elementLabel(element, language)}
    </button>
  );
}

interface ElementDetailContentProps {
  element: ElementDetail;
  /** All elements of the ontology, to list properties, relations, parent and child types. */
  related: UseQueryResult<Element[]>;
  onSelect: (id: string) => void;
}

function ElementDetailContent({ element, related, onSelect }: ElementDetailContentProps) {
  const { t, i18n } = useTranslation();
  const all = related.data ?? [];
  const language = i18n.resolvedLanguage ?? i18n.language;
  const byId = new Map(all.map((item) => [item.id, item]));
  const properties = all.filter((item) => item.kind === 'property' && item.domainId === element.id);
  const outgoing = all.filter((item) => item.kind === 'relation_type' && item.domainId === element.id);
  const incoming = all.filter((item) => item.kind === 'relation_type' && item.rangeId === element.id);
  const children = all.filter((item) => item.kind === 'entity_type' && item.parentId === element.id);
  const cardinality = [element.required ? t('review.facts.required') : null, element.multiple ? t('review.facts.multiple') : null].filter(
    (value): value is string => value !== null,
  );

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={kindTone[element.kind]}>{t(`kinds.${element.kind}`)}</Badge>
          {element.status === 'deprecated' ? <Badge tone="warning">{t('ontologyPage.detail.deprecated')}</Badge> : null}
        </div>
        <DialogTitle className="text-xl">{element.labelZh}</DialogTitle>
        <DialogDescription className="mt-0">
          {element.labelEn ? <span className="mr-2">{element.labelEn}</span> : null}
          <span className="font-mono text-xs">{element.localName}</span>
        </DialogDescription>
        <p className="break-all font-mono text-xs text-muted-foreground">{element.iri}</p>
      </div>

      <Section title={t('ontologyPage.detail.definition')}>
        {element.definitionZh || element.definitionEn ? (
          <div className="space-y-1 text-sm text-foreground">
            {element.definitionZh ? <p>{element.definitionZh}</p> : null}
            {element.definitionEn ? <p className="text-muted-foreground">{element.definitionEn}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.noDefinition')}</p>
        )}
      </Section>

      <Section title={t('ontologyPage.detail.synonyms')}>
        {element.synonyms.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {element.synonyms.map((synonym) => (
              <li key={`${synonym.lang}-${synonym.text}`} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-sm">
                <span className="text-[0.6875rem] font-semibold uppercase text-muted-foreground">{synonym.lang}</span>
                {synonym.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.noSynonyms')}</p>
        )}
      </Section>

      <Section title={t('ontologyPage.detail.structure')}>
        <QueryState query={related} loading={<Skeleton className="h-24 rounded-lg" />}>
          {() =>
      element.kind === 'entity_type' ? (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">{t('ontologyPage.detail.parent')}</dt>
            <dd>
              {element.parentId ? <ElementLink element={byId.get(element.parentId)} onSelect={onSelect} language={language} /> : '—'}
            </dd>
            <dt className="text-muted-foreground">{t('ontologyPage.detail.children')}</dt>
            <dd className="flex flex-wrap gap-x-3 gap-y-1">
              {children.length > 0
                ? children.map((child) => <ElementLink key={child.id} element={child} onSelect={onSelect} language={language} />)
                : '—'}
            </dd>
          </dl>
          <h4 className="pt-2 text-xs font-semibold text-muted-foreground">{t('ontologyPage.detail.properties', { count: properties.length })}</h4>
          {properties.length > 0 ? (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {properties.map((property) => (
                <li key={property.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-sm">
                  <ElementLink element={property} onSelect={onSelect} language={language} />
                  {property.datatype ? <Badge tone="neutral">{t(`datatypes.${property.datatype}`)}</Badge> : null}
                  {property.unit ? <span className="text-xs text-muted-foreground">{property.unit}</span> : null}
                  {property.required ? <span className="text-xs text-muted-foreground">{t('review.facts.required')}</span> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.none')}</p>
          )}
          <h4 className="pt-2 text-xs font-semibold text-muted-foreground">
            {t('ontologyPage.detail.relations', { count: outgoing.length + incoming.length })}
          </h4>
          {outgoing.length + incoming.length > 0 ? (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {[...outgoing, ...incoming].map((relation) => (
                <li key={relation.id} className="flex flex-wrap items-center gap-1.5 px-3 py-2 text-sm">
                  <ElementLink element={relation.domainId ? byId.get(relation.domainId) : undefined} onSelect={onSelect} language={language} />
                  <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                  <ElementLink element={relation} onSelect={onSelect} language={language} />
                  <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                  <ElementLink element={relation.rangeId ? byId.get(relation.rangeId) : undefined} onSelect={onSelect} language={language} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.none')}</p>
          )}
        </>
      ) : (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">
              {t(element.kind === 'property' ? 'review.fields.propertyDomainRef' : 'review.fields.domainRef')}
            </dt>
            <dd>
              <ElementLink element={element.domainId ? byId.get(element.domainId) : undefined} onSelect={onSelect} language={language} />
            </dd>
            {element.kind === 'relation_type' ? (
              <>
                <dt className="text-muted-foreground">{t('review.fields.rangeRef')}</dt>
                <dd>
                  <ElementLink element={element.rangeId ? byId.get(element.rangeId) : undefined} onSelect={onSelect} language={language} />
                </dd>
              </>
            ) : (
              <>
                <dt className="text-muted-foreground">{t('review.fields.datatype')}</dt>
                <dd>{element.datatype ? t(`datatypes.${element.datatype}`) : '—'}</dd>
                <dt className="text-muted-foreground">{t('review.fields.unit')}</dt>
                <dd>{element.unit ?? '—'}</dd>
              </>
            )}
            <dt className="text-muted-foreground">{t('ontologyPage.detail.cardinality')}</dt>
            <dd>{cardinality.length > 0 ? cardinality.join(t('common.listSeparator')) : t('ontologyPage.detail.optionalSingle')}</dd>
          </dl>
        </>
      )
          }
        </QueryState>
      </Section>

      <Section title={t('ontologyPage.detail.provenance')}>
        {element.provenance.length > 0 ? (
          <ul className="space-y-3">
            {element.provenance.map((entry) => (
              <li key={entry.itemId} className="space-y-2 rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  <GitMerge className="size-4 text-muted-foreground" aria-hidden />
                  <Link
                    to="/review/$changeSetId"
                    params={{ changeSetId: entry.changeSetId }}
                    className="rounded font-medium text-primary-strong hover:underline"
                  >
                    {entry.changeSetTitle}
                  </Link>
                  <Badge tone={entry.op === 'create' ? 'primary' : 'secondary'}>{t(`review.op.${entry.op}`)}</Badge>
                  <span className="text-xs text-muted-foreground">
                    <RelativeTime value={entry.mergedAt} />
                  </span>
                </div>
                {entry.evidence.map((evidence) => (
                  <ProvenanceEvidence key={evidence.id} evidence={evidence} />
                ))}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.noProvenance')}</p>
        )}
      </Section>
    </div>
  );
}

/** A quote that expands into the highlighted source chunk on demand. */
function ProvenanceEvidence({ evidence }: { evidence: Evidence }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <blockquote className="border-l-2 border-info pl-3 text-sm text-foreground">{evidence.quote}</blockquote>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary-strong hover:underline"
      >
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
        {open ? t('ontologyPage.detail.hideSource') : t('ontologyPage.detail.showSource')}
      </button>
      {open ? <EvidenceExcerpt evidence={evidence} /> : null}
    </div>
  );
}
