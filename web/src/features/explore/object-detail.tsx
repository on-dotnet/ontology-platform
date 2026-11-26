import { ChevronDown, ChevronRight } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { components } from '@/api/schema';
import { Button } from '@/components/ui/button';

import { useDetail, useRelated } from './api';
import { keyLabel, PropertyValue } from './object-values';
import { QueryResult } from './query-result';

type ObjectRow = components['schemas']['ObjectRow'];
type ObjectTypeInfo = components['schemas']['ObjectTypeInfo'];
type ObjectRelation = components['schemas']['ObjectRelation'];

interface ObjectDetailPanelProps {
  id: string;
  releaseId: string;
  row: ObjectRow;
  types: ObjectTypeInfo[];
  onOpen: (row: ObjectRow) => void;
  onRestart: () => void;
}

type RelationProps = Omit<ObjectDetailPanelProps, 'types'> & { relation: ObjectRelation };

function RelatedObjects({ id, releaseId, row, relation, onOpen, onRestart }: RelationProps) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState<string | null>(null);
  const query = useRelated(id, releaseId, row.typeId, row.key, relation, cursor);

  return (
    <QueryResult query={query} id={id} onRestart={onRestart} onFirstPage={cursor !== null ? () => setCursor(null) : undefined}>
      {(page) => (
        <div className="space-y-2">
          {page.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('explore.detail.noRelated')}</p>
          ) : (
            <ul className="divide-y divide-border">
              {page.items.map((item) => (
                <li key={item.key}>
                  <Button
                    variant="ghost"
                    className="h-auto min-h-10 max-w-full justify-start whitespace-normal break-all text-left text-primary-strong"
                    onClick={() => onOpen(item)}
                  >
                    {keyLabel(item)}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {page.nextCursor !== null && (
            <Button variant="secondary" size="sm" onClick={() => setCursor(page.nextCursor)}>
              {t('explore.nextPage')}
            </Button>
          )}
        </div>
      )}
    </QueryResult>
  );
}

function RelationGroup(props: RelationProps) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <li>
      <Button
        variant="ghost"
        className="h-auto min-h-10 w-full justify-start whitespace-normal break-words text-left text-foreground"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((open) => !open)}
      >
        <Chevron aria-hidden />
        {props.relation.label}
      </Button>
      <div id={contentId} hidden={!expanded} className="pb-3 pl-6">
        {expanded && <RelatedObjects {...props} />}
      </div>
    </li>
  );
}

export function ObjectDetailPanel({ types, ...context }: ObjectDetailPanelProps) {
  const { t } = useTranslation();
  const { id, releaseId, row, onRestart } = context;
  const query = useDetail(id, releaseId, row.typeId, row.key);

  return (
    <QueryResult query={query} id={id} onRestart={onRestart}>
      {(detail) => {
        const properties = types.find((type) => type.typeId === detail.typeId)?.properties ?? [];
        const source = detail.source;
        return (
          <div className="space-y-6">
            <section aria-label={t('explore.detail.properties')} className="space-y-2">
              <h3 className="text-base font-semibold">{t('explore.detail.properties')}</h3>
              {properties.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('explore.detail.noProperties')}</p>
              ) : (
                <dl className="divide-y divide-border">
                  {properties.map((property) => (
                    <div key={property.propertyId} className="grid gap-1 py-2 text-sm sm:grid-cols-2 sm:gap-4">
                      <dt className="break-words text-muted-foreground">{property.label}{property.unit && ` (${property.unit})`}</dt>
                      <dd className="min-w-0 break-words tabular-nums">
                        <PropertyValue property={property} row={detail} />
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
            <section aria-label={t('explore.detail.source')} className="space-y-2">
              <h3 className="text-base font-semibold">{t('explore.detail.source')}</h3>
              <p className="break-all text-sm text-muted-foreground">
                {t('explore.detail.sourceLine', {
                  name: source.dataSourceName,
                  table: `${source.schema}.${source.table}`,
                  key: keyLabel(detail, { withColumns: true }),
                })}
              </p>
            </section>
            <section aria-label={t('explore.detail.relations')} className="space-y-2">
              <h3 className="text-base font-semibold">{t('explore.detail.relations')}</h3>
              {detail.relations.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('explore.detail.noRelations')}</p>
              ) : (
                <ul className="divide-y divide-border">
                  {detail.relations.map((relation) => (
                    <RelationGroup key={`${relation.relationId}:${relation.direction}`} {...context} relation={relation} />
                  ))}
                </ul>
              )}
            </section>
          </div>
        );
      }}
    </QueryResult>
  );
}
