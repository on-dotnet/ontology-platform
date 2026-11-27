import { Link } from '@tanstack/react-router';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InfoTip, WarnTip } from '@/components/feedback/hint-tip';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { ErrorState } from '@/components/states/error-state';
import { QueryState } from '@/components/states/query-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Pagination } from '@/components/ui/pagination';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePermissions } from '@/features/auth/permissions';
import { elementName, type Element } from '@/features/ontologies/api';
import { usePagination } from '@/lib/pagination';

import { tableName, useBindingViews, type CatalogCheck, type Join, type TableBindingView, type TypeBindingView } from './api';
import { BindingDialog } from './binding-dialog';
import { SuggestBindingsDialog } from './suggest/suggest-bindings-dialog';

export interface BindingSectionProps {
  ontologyId: string;
  /** The object type the detail panel shows. */
  type: Element;
  /** Active elements of the ontology, for names in the reader's language; undefined while they load. */
  all: readonly Element[] | undefined;
}

/**
 * "Data binding" block of an object type's detail panel (spec 003, 12.2): the working version's
 * table, key columns, property columns and relation joins, with catalog checks; editors bind
 * and edit through a manual change set, which goes to review unless they may apply their own edits.
 */
export function BindingSection(props: BindingSectionProps) {
  return props.type.status === 'active' ? <ActiveBindingSection key={props.type.id} {...props} /> : null;
}

function ActiveBindingSection({ ontologyId, type, all }: BindingSectionProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const { canEditBindings } = usePermissions();
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [editing, setEditing] = useState<{ view: TypeBindingView; all: readonly Element[] } | null>(null);
  const views = useBindingViews(ontologyId, type.id);

  return (
    <section aria-labelledby={titleId} className="space-y-2 border-t border-border pt-4">
      <div className="flex items-center gap-1">
        <h3 id={titleId} className="text-sm font-semibold text-foreground">{t('bindings.title')}</h3>
        <InfoTip>{t('bindings.info')}</InfoTip>
      </div>
      <QueryState
        query={views}
        errorTitle={t('bindings.loadFailed')}
        loading={
          <div role="status" aria-label={t('common.loading')} aria-busy>
            <Skeleton className="h-24 rounded-lg" />
          </div>
        }
      >
        {([view]) => {
          if (view?.typeId !== type.id) {
            return <ErrorState error={null} title={t('bindings.loadFailed')} onRetry={() => void views.refetch()} />;
          }
          return (
            <>
              {view.table ? (
                <>
                  <TableDetails table={view.table} />
                  <PropertyAndRelationBindings view={view} all={all} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t('bindings.empty')}</p>
              )}
              <PendingChanges ontologyId={ontologyId} changeSetIds={view.openChangeSetIds} />
              {canEditBindings ? (
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" size="sm" aria-haspopup="dialog" disabled={!all}
                    onClick={() => { if (all) setEditing({ view, all }); }}>
                    {t(view.table ? 'bindings.edit' : 'bindings.bind')}
                  </Button>
                  {!view.table && (
                    <Button variant="secondary" size="sm" aria-haspopup="dialog" onClick={() => setSuggestOpen(true)}>
                      {t('bindings.suggest.title')}
                    </Button>
                  )}
                  {!view.table && suggestOpen && (
                    <SuggestBindingsDialog open onOpenChange={setSuggestOpen} ontologyId={ontologyId} typeIds={[type.id]} />
                  )}
                </div>
              ) : null}
            </>
          );
        }}
      </QueryState>
      {canEditBindings && editing && (
        <BindingDialog ontologyId={ontologyId} type={type} all={editing.all} view={editing.view} open
          onOpenChange={(next) => { if (!next) setEditing(null); }} />
      )}
    </section>
  );
}

/** One waiting change set is opened directly; the view carries no titles to tell several apart, the review list does. */
function PendingChanges({ ontologyId, changeSetIds }: { ontologyId: string; changeSetIds: string[] }) {
  const { t } = useTranslation();
  const [changeSetId] = changeSetIds;
  if (!changeSetId) return null;
  const className = 'rounded font-medium text-primary-strong hover:underline';
  return (
    <InlineNotice tone="info" title={t('bindings.pending.title')} announce={false}>
      {changeSetIds.length > 1 ? (
        <Link to="/review" search={{ ontology: ontologyId }} className={className}>
          {t('bindings.pending.listLink', { count: changeSetIds.length })}
        </Link>
      ) : (
        <Link to="/review/$changeSetId" params={{ changeSetId }} className={className}>{t('bindings.pending.link')}</Link>
      )}
    </InlineNotice>
  );
}

function CheckTip({ check }: { check: CatalogCheck }) {
  const { t } = useTranslation();
  if (check === 'ok') return null;
  const message = t(`bindings.check.${check}`);
  return <WarnTip label={message}>{message}</WarnTip>;
}

function TableDetails({ table }: { table: TableBindingView }) {
  const { t } = useTranslation();
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">{t('bindings.table.dataSource')}</dt>
      <dd className="flex flex-wrap items-center gap-1.5">
        <span className="break-all">{table.dataSource.name}</span>
        {table.dataSource.status === 'archived' ? <Badge>{t('bindings.table.archived')}</Badge> : null}
      </dd>
      <dt className="text-muted-foreground">{t('bindings.table.table')}</dt>
      <dd className="flex flex-wrap items-center gap-1">
        <code className="break-all">{tableName(table.schema, table.table)}</code>
        <CheckTip check={table.check} />
      </dd>
      <dt className="text-muted-foreground">{t('bindings.table.keyColumns')}</dt>
      <dd className="flex flex-wrap gap-1">
        {table.keyColumns.map((column) => (
          <Badge key={column} className="h-auto min-h-6 max-w-full whitespace-normal break-all font-mono">{column}</Badge>
        ))}
      </dd>
    </dl>
  );
}

function PropertyAndRelationBindings({ view, all }: { view: TypeBindingView; all: BindingSectionProps['all'] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;
  const byId = new Map(all?.map((element) => [element.id, element]));
  const nameOf = (id: string, label: string) => {
    const element = byId.get(id);
    return (element && elementName(element, language)) || label || t('ontologyPage.detail.unknownElement');
  };
  const propertyPage = usePagination(view.properties.length, view.typeId);
  const relationPage = usePagination(view.relations.length, view.typeId);
  return (
    <>
      <div>
        <Table>
          <caption className="pb-1 text-left text-sm font-medium">{t('bindings.properties.title')}</caption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('bindings.properties.property')}</TableHead>
              <TableHead>{t('bindings.properties.column')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {view.properties.slice(propertyPage.start, propertyPage.end).map(({ propertyId, label, inherited, column }) => (
              <TableRow key={propertyId}>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="break-all">{nameOf(propertyId, label)}</span>
                    {inherited ? <Badge>{t('bindings.properties.inherited')}</Badge> : null}
                  </div>
                </TableCell>
                <TableCell>
                  {column ? (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <code className="break-all">{column.column}</code>
                      {column.columnType ? <code className="break-all text-xs text-muted-foreground">{column.columnType}</code> : null}
                      <CheckTip check={column.check} />
                    </div>
                  ) : (
                    <span className="text-muted-foreground">{t('bindings.properties.unbound')}</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {view.properties.length === 0 ? (
              <TableRow>
                <TableCell colSpan={2} className="text-muted-foreground">{t('ontologyPage.detail.none')}</TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        <Pagination state={propertyPage} total={view.properties.length} />
      </div>
      <div className="space-y-1 text-sm">
        <h4 className="font-medium">{t('bindings.relations.title')}</h4>
        {view.relations.length === 0 ? (
          <p className="text-muted-foreground">{t('ontologyPage.detail.none')}</p>
        ) : (
          <ul aria-label={t('bindings.relations.title')} className="divide-y divide-border">
            {view.relations.slice(relationPage.start, relationPage.end).map((relation) => (
              <li key={`${relation.relationId}-${relation.direction}-${relation.otherTypeId}`} className="space-y-0.5 py-1">
                <p className="break-words">
                  {t(`bindings.relations.${relation.direction}`, {
                    relation: nameOf(relation.relationId, relation.label),
                    type: nameOf(relation.otherTypeId, relation.otherTypeLabel),
                  })}
                </p>
                {relation.join ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <JoinDescription join={relation.join.join} />
                    <CheckTip check={relation.join.check} />
                  </div>
                ) : (
                  <p className="text-muted-foreground">{t('bindings.relations.unbound')}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        <Pagination state={relationPage} total={view.relations.length} />
      </div>
    </>
  );
}

function JoinDescription({ join }: { join: Join }) {
  const { t } = useTranslation();
  const separator = t('common.listSeparator');
  const description = join.kind === 'foreign_key'
    ? t('bindings.relations.foreignKey', { columns: join.columns.join(separator), references: join.references.join(separator) })
    : t('bindings.relations.linkTable', { table: tableName(join.schema, join.table) });
  return <span className="break-all text-xs">{description}</span>;
}
