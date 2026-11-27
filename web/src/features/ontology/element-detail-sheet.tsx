import type { UseQueryResult } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowRight, ChevronDown, GitMerge, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { WarnTip } from '@/components/feedback/hint-tip';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogDescription, DialogTitle, SheetContent } from '@/components/ui/dialog';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { usePermissions } from '@/features/auth/permissions';
import { BindingSection } from '@/features/bindings/binding-section';
import { EvidenceExcerpt } from '@/features/documents/evidence-excerpt';
import {
  elementName,
  useElementDetail,
  useElements,
  type Element,
  type ElementDetail,
  type Evidence,
} from '@/features/ontologies/api';
import { OpBadge } from '@/features/review/item-badges';
import { cn } from '@/lib/cn';

import { AxiomFormDialog } from './axiom-form-dialog';
import { useRestoreElement } from './edit-actions';
import { AxiomBadge, AxiomFragment, ConstraintRules } from './element-content';
import { isFormKind } from './element-form';
import { ElementFormDialog } from './element-form-dialog';
import { DeleteElementDialog, ReferencedBy } from './element-impact';
import { kindTone } from './element-list';
import { MetricDefinition, metricFields } from './metric-definition';

interface ElementDetailSheetProps {
  ontologyId: string;
  /** The element shown; the sheet is closed when null. */
  elementId: string | null;
  onSelect: (elementId: string) => void;
  onClose: () => void;
}

/** Side panel with an element's definition, synonyms, structure, rules or Turtle, related axioms and evidence. */
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
        {(element) => <ElementDetailContent ontologyId={ontologyId} element={element} related={all} onSelect={onSelect} />}
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

interface RefLinkProps {
  /** Element id; a dash when unset. */
  id: string | null;
  byId: ReadonlyMap<string, Element>;
  onSelect: (id: string) => void;
  language: string;
}

/** Link to a referenced element in the same panel; "unknown" when it is not among the active elements. */
function RefLink({ id, byId, onSelect, language }: RefLinkProps) {
  const { t } = useTranslation();
  if (!id) return <span className="text-muted-foreground">—</span>;
  const element = byId.get(id);
  if (!element) return <span className="text-muted-foreground">{t('ontologyPage.detail.unknownElement')}</span>;
  return <ElementLink element={element} onSelect={onSelect} language={language} />;
}

function ElementLink({ element, onSelect, language }: { element: Element; onSelect: (id: string) => void; language: string }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(element.id)}
      className={cn('rounded text-left font-medium text-primary-strong hover:underline', element.kind === 'axiom' && 'font-mono text-xs')}
    >
      {elementName(element, language) || '—'}
    </button>
  );
}

interface ElementDetailContentProps {
  ontologyId: string;
  element: ElementDetail;
  /** All elements of the ontology, to list properties, relations, parent and child types, and axioms. */
  related: UseQueryResult<Element[]>;
  onSelect: (id: string) => void;
}

function ElementDetailContent({ ontologyId, element, related, onSelect }: ElementDetailContentProps) {
  const { t, i18n } = useTranslation();
  const { canUpload } = usePermissions();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { restore, pendingId, apply: restoresAtOnce } = useRestoreElement(ontologyId);
  const deleted = element.status === 'deprecated';
  const language = i18n.resolvedLanguage ?? i18n.language;
  const isAxiom = element.kind === 'axiom';
  const title = isAxiom ? t('ontologyPage.detail.axiomTitle') : elementName(element, language) || '—';
  // The name in the other language, whichever one the title shows.
  const other = language.startsWith('en') ? element.labelZh : element.labelEn;
  const secondary = other && other !== title ? other : null;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          {isAxiom ? <AxiomBadge category={element.axiomCategory} /> : <Badge tone={kindTone[element.kind]}>{t(`kind.${element.kind}`)}</Badge>}
          {element.status === 'deprecated' ? <Badge tone="warning">{t('ontologyPage.detail.deprecated')}</Badge> : null}
          {element.flags.includes('non_standard') ? (
            <WarnTip label={t('review.flags.non_standard.label')}>{t('review.flags.non_standard.description')}</WarnTip>
          ) : null}
        </div>
        <DialogTitle className="text-xl">{title}</DialogTitle>
        {secondary || element.localName ? (
          <DialogDescription className="mt-0">
            {secondary ? <span className="mr-2">{secondary}</span> : null}
            {element.localName ? <span className="font-mono text-xs">{element.localName}</span> : null}
          </DialogDescription>
        ) : null}
        {element.iri ? (
          <dl className="flex gap-2 text-xs">
            <dt className="shrink-0 font-semibold text-muted-foreground">{t('ontologyPage.detail.iri')}</dt>
            <dd className="min-w-0 break-all font-mono text-muted-foreground">{element.iri}</dd>
          </dl>
        ) : null}
        {canUpload ? (
          <div className="flex flex-wrap gap-2 pt-2">
            {deleted ? (
              <Button variant="secondary" size="sm" loading={pendingId === element.id} onClick={() => restore(element)}>
                <RotateCcw aria-hidden />
                {restoresAtOnce ? t('ontologyPage.edit.restore') : t('ontologyPage.edit.submitRestore')}
              </Button>
            ) : (
              <>
                {/* Axioms are edited as Turtle (expert mode), the other kinds with the element form. */}
                <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                  <Pencil aria-hidden />
                  {t('ontologyPage.edit.edit')}
                </Button>
                <Button variant="secondary" size="sm" className="text-error-strong" onClick={() => setDeleting(true)}>
                  <Trash2 aria-hidden />
                  {t('ontologyPage.edit.delete')}
                </Button>
              </>
            )}
          </div>
        ) : null}
      </div>
      {canUpload ? (
        <>
          {isFormKind(element.kind) ? (
            <ElementFormDialog ontologyId={ontologyId} target={editing ? { elementId: element.id } : null} onClose={() => setEditing(false)} />
          ) : (
            <AxiomFormDialog ontologyId={ontologyId} open={editing} elementId={element.id} onClose={() => setEditing(false)} />
          )}
          <DeleteElementDialog ontologyId={ontologyId} element={element} all={related.data} open={deleting} onOpenChange={setDeleting} />
        </>
      ) : null}

      {isAxiom ? (
        <AxiomSections element={element} related={related} onSelect={onSelect} language={language} />
      ) : (
        <>
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

          {element.kind !== 'metric' && <Section title={t('ontologyPage.detail.synonyms')}>
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
          </Section>}

          {element.kind === 'metric' ? (
            <Section title={t('ontologyMetric.definition')}>
              <QueryState query={related} loading={<Skeleton className="h-24 rounded-lg" />}>
                {(all) => {
                  const byId = new Map(all.map((item) => [item.id, item]));
                  return <MetricDefinition
                    fields={{ subjectRef: element.subjectId, metric: element.metric && metricFields(element.metric), unit: element.unit }}
                    nameOf={(ref) => {
                      const item = byId.get(ref);
                      return item && elementName(item, language);
                    }}
                    linkTo={(ref) => <RefLink id={ref} byId={byId} language={language} onSelect={onSelect} />}
                  />;
                }}
              </QueryState>
            </Section>
          ) : element.kind === 'constraint' ? (
            <Section title={t('ontologyPage.detail.rules')}>
              <QueryState query={related} loading={<Skeleton className="h-24 rounded-lg" />}>
                {(all) => <ConstraintSection element={element} all={all} onSelect={onSelect} language={language} />}
              </QueryState>
            </Section>
          ) : (
            <Section title={t('ontologyPage.detail.structure')}>
              <QueryState query={related} loading={<Skeleton className="h-24 rounded-lg" />}>
                {(all) => <StructureSection element={element} all={all} onSelect={onSelect} language={language} />}
              </QueryState>
            </Section>
          )}

          {element.kind === 'entity_type' ? <BindingSection ontologyId={ontologyId} type={element} all={related.data} /> : null}

          <Section title={t('ontologyPage.impact.title')}>
            <QueryState query={related} loading={<Skeleton className="h-16 rounded-lg" />}>
              {(all) => <ReferencedBy ontologyId={ontologyId} element={element} all={all} onSelect={onSelect} />}
            </QueryState>
          </Section>

          {element.kind !== 'metric' && <Section title={t('ontologyPage.detail.relatedAxioms')}>
            <QueryState query={related} loading={<Skeleton className="h-16 rounded-lg" />}>
              {(all) => <RelatedAxioms element={element} all={all} onSelect={onSelect} />}
            </QueryState>
          </Section>}
        </>
      )}

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
                  <OpBadge op={entry.op} />
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

interface KindSectionProps {
  element: ElementDetail;
  all: readonly Element[];
  onSelect: (id: string) => void;
  language: string;
}

/** Parent and child types, properties and relations; or a relation's / property's references. */
function StructureSection({ element, all, onSelect, language }: KindSectionProps) {
  const { t } = useTranslation();
  const byId = new Map(all.map((item) => [item.id, item]));
  const ref = (id: string | null) => <RefLink id={id} byId={byId} onSelect={onSelect} language={language} />;

  if (element.kind === 'entity_type') {
    const properties = all.filter((item) => item.kind === 'property' && item.domainId === element.id);
    const outgoing = all.filter((item) => item.kind === 'relation_type' && item.domainId === element.id);
    const incoming = all.filter((item) => item.kind === 'relation_type' && item.rangeId === element.id);
    const children = all.filter((item) => item.kind === 'entity_type' && item.parentId === element.id);
    return (
      <>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t('ontologyPage.detail.parent')}</dt>
          <dd>{ref(element.parentId)}</dd>
          <dt className="text-muted-foreground">{t('ontologyPage.detail.children')}</dt>
          <dd className="flex flex-wrap gap-x-3 gap-y-1">
            {children.length > 0 ? children.map((child) => <ElementLink key={child.id} element={child} onSelect={onSelect} language={language} />) : '—'}
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
                {ref(relation.domainId)}
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                <ElementLink element={relation} onSelect={onSelect} language={language} />
                <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                {ref(relation.rangeId)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.none')}</p>
        )}
      </>
    );
  }

  const cardinality = [element.required ? t('review.facts.required') : null, element.multiple ? t('review.facts.multiple') : null].filter(
    (value): value is string => value !== null,
  );
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">{t(element.kind === 'property' ? 'review.fields.propertyDomainRef' : 'review.fields.domainRef')}</dt>
      <dd>{ref(element.domainId)}</dd>
      {element.kind === 'relation_type' ? (
        <>
          <dt className="text-muted-foreground">{t('review.fields.rangeRef')}</dt>
          <dd>{ref(element.rangeId)}</dd>
          <dt className="text-muted-foreground">{t('review.fields.inverseRef')}</dt>
          <dd>{ref(element.inverseId)}</dd>
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
  );
}

/** Target type and the rule table of a constraint. */
function ConstraintSection({ element, all, onSelect, language }: KindSectionProps) {
  const { t } = useTranslation();
  const byId = new Map(all.map((item) => [item.id, item]));
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">{t('review.fields.targetRef')}</dt>
        <dd>
          <RefLink id={element.domainId} byId={byId} onSelect={onSelect} language={language} />
        </dd>
      </dl>
      <ConstraintRules
        rules={element.rules ?? []}
        nameOf={(id) => {
          const target = byId.get(id);
          return target ? elementName(target, language) : undefined;
        }}
      />
    </div>
  );
}

/** Axioms whose subject is this element. */
function RelatedAxioms({ element, all, onSelect }: { element: ElementDetail; all: readonly Element[]; onSelect: (id: string) => void }) {
  const { t } = useTranslation();
  const axioms = all.filter((item) => item.kind === 'axiom' && item.subjectId === element.id);
  if (axioms.length === 0) return <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.noRelatedAxioms')}</p>;
  return (
    <ul className="divide-y divide-border rounded-lg border border-border">
      {axioms.map((axiom) => (
        <li key={axiom.id} className="flex items-center gap-1.5 px-3 py-2">
          <button
            type="button"
            onClick={() => onSelect(axiom.id)}
            className="min-w-0 rounded text-left text-primary-strong hover:underline"
          >
            <AxiomBadge category={axiom.axiomCategory} />
          </button>
          {axiom.axiomNote ? <span className="text-sm">{axiom.axiomNote}</span> : null}
          {axiom.flags.includes('non_standard') ? (
            <WarnTip label={t('review.flags.non_standard.label')}>{t('review.flags.non_standard.description')}</WarnTip>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** The Turtle of an axiom and the element it belongs to. */
function AxiomSections({ element, related, onSelect, language }: Omit<KindSectionProps, 'all'> & { related: UseQueryResult<Element[]> }) {
  const { t } = useTranslation();
  return (
    <>
      <div>
        {element.axiomNote ? <p className="text-sm">{element.axiomNote}</p> : null}
        <AxiomFragment turtle={element.turtle} />
      </div>
      <Section title={t('ontologyPage.detail.subject')}>
        {element.subjectId ? (
          <QueryState query={related} loading={<Skeleton className="h-5 w-32 rounded" />}>
            {(all) => (
              <p className="text-sm">
                <RefLink id={element.subjectId} byId={new Map(all.map((item) => [item.id, item]))} onSelect={onSelect} language={language} />
              </p>
            )}
          </QueryState>
        ) : (
          <p className="text-sm text-muted-foreground">{t('ontologyPage.detail.noSubject')}</p>
        )}
      </Section>
    </>
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
