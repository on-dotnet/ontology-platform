import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useRouterState } from '@tanstack/react-router';
import { Network, ShieldCheck, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { NavItem } from '@/app/navigation';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { EmptyState } from '@/components/states/empty-state';
import { QueryState } from '@/components/states/query-state';
import { buttonVariants } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { usePermissions } from '@/features/auth/permissions';
import { elementName, useElementDetail, type ElementDetail, type OntologySummary } from '@/features/ontologies/api';
import { useSelectedOntology } from '@/features/ontologies/use-selected-ontology';
import { optionalString } from '@/lib/search';

import { createAssistantRequest, storeRequest, useAssistantRequests, type AssistantRequest, type AssistantRequestCreate } from './api';
import { useAssistantSelection } from './assistant-selection';
import { Composer } from './composer';
import { RequestEntry } from './request-entry';

function PanelSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy className="space-y-3 p-4">
      <span className="sr-only">{t('common.loading')}</span>
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-20 rounded-lg" />
      <Skeleton className="h-16 rounded-lg" />
    </div>
  );
}

/**
 * The assistant for the ontology the user works on: the one the page published, else the one in
 * the URL, else the first, as the pages themselves choose it.
 */
export function AssistantWorkspace({ page }: { page: NavItem['key'] }) {
  const { t } = useTranslation();
  const { canUpload } = usePermissions();
  const selection = useAssistantSelection();
  const search = useRouterState({ select: (state) => state.location.search as Record<string, unknown> });
  const { query, selected } = useSelectedOntology(selection.ontologyId ?? optionalString(search.ontology));

  return (
    <QueryState query={query} loading={<PanelSkeleton />}>
      {() =>
        selected ? (
          <OntologyAssistant
            key={selected.id}
            ontology={selected}
            page={page}
            elementId={selection.ontologyId === selected.id ? (selection.elementId ?? null) : null}
            canAsk={canUpload}
          />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <EmptyState
              icon={Network}
              tone="info"
              title={t('assistant.noOntologyTitle')}
              description={t('assistant.noOntologyDescription')}
              headingLevel="h3"
              className="py-10"
              action={
                canUpload ? (
                  <Link to="/ontology" className={buttonVariants({ variant: 'primary', size: 'sm' })}>
                    {t('assistant.goToOntology')}
                  </Link>
                ) : undefined
              }
            />
          </div>
        )
      }
    </QueryState>
  );
}

interface OntologyAssistantProps {
  ontology: OntologySummary;
  page: NavItem['key'];
  elementId: string | null;
  /** Editors, reviewers and admins may ask for changes; viewers only read. */
  canAsk: boolean;
}

function OntologyAssistant({ ontology, page, elementId, canAsk }: OntologyAssistantProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const requests = useAssistantRequests(ontology.id);
  // Only an element that still exists is context; one deleted meanwhile is left out.
  const detail = useElementDetail(ontology.id, elementId ?? undefined);
  const element = elementId && detail.data?.id === elementId && detail.data.status === 'active' ? detail.data : undefined;
  // The failed request being sent again; null while sending from the composer.
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (body: AssistantRequestCreate) => createAssistantRequest(ontology.id, body),
    onSuccess: (created) => storeRequest(queryClient, created),
  });

  const send = (message: string) => {
    setRetryingId(null);
    return create.mutateAsync({ message, context: { page, elementId: element?.id ?? null } });
  };

  // The same words in the same context as the first time.
  const retry = (request: AssistantRequest) => {
    setRetryingId(request.id);
    create.mutate({ message: request.message, context: { page: request.context.page, elementId: request.context.elementId ?? null } });
  };

  return (
    <>
      <ContextBar ontology={ontology} element={element} />
      <div className="shrink-0 border-b border-border p-4">
        {canAsk ? (
          <Composer onSend={send} sending={create.isPending && retryingId === null} sendError={create.isError ? create.error : null} />
        ) : (
          <InlineNotice tone="info" title={t('assistant.viewerTitle')}>
            {t('assistant.viewerDescription')}
          </InlineNotice>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <QueryState query={requests} loading={<PanelSkeleton />}>
          {(list) =>
            list.length === 0 ? (
              canAsk ? (
                <div className="flex flex-col items-center px-2 py-6 text-center">
                  <span className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-info-soft text-info-strong">
                    <Sparkles className="size-5" aria-hidden />
                  </span>
                  <h3 className="text-sm font-semibold text-foreground">{t('assistant.emptyTitle')}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{t('assistant.emptyDescription')}</p>
                  <p className="mt-4 flex gap-2 text-left text-xs text-muted-foreground">
                    <ShieldCheck className="size-4 shrink-0" aria-hidden />
                    <span>{t('assistant.reviewNote')}</span>
                  </p>
                </div>
              ) : null
            ) : (
              <ol aria-label={t('assistant.listLabel')} className="space-y-5">
                {list.map((request) => (
                  <RequestEntry
                    key={request.id}
                    request={request}
                    onRetry={canAsk ? () => retry(request) : undefined}
                    retrying={create.isPending && retryingId === request.id}
                  />
                ))}
              </ol>
            )
          }
        </QueryState>
      </div>
    </>
  );
}

/** What the assistant takes as context besides the page: the ontology and the selected element. */
function ContextBar({ ontology, element }: { ontology: OntologySummary; element: ElementDetail | undefined }) {
  const { t, i18n } = useTranslation();
  const name = element ? elementName(element, i18n.resolvedLanguage ?? i18n.language) : '';

  return (
    <dl className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 border-b border-border px-4 py-2.5 text-xs">
      <div className="flex min-w-0 gap-1.5">
        <dt className="shrink-0 text-muted-foreground">{t('assistant.ontologyLabel')}</dt>
        <dd className="truncate font-medium text-foreground">{ontology.name}</dd>
      </div>
      {name ? (
        <div className="flex min-w-0 gap-1.5">
          <dt className="shrink-0 text-muted-foreground">{t('assistant.elementLabel')}</dt>
          <dd className="truncate font-medium text-foreground">{name}</dd>
        </div>
      ) : null}
    </dl>
  );
}
