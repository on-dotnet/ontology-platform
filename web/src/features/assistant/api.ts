import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/schema';
import { ontologyKeys } from '@/features/ontologies/api';
import { changeSetKeys } from '@/features/review/api';

export type AssistantRequest = components['schemas']['AssistantRequest'];
export type AssistantRequestCreate = components['schemas']['AssistantRequestCreate'];
export type AssistantStep = NonNullable<AssistantRequest['step']>;

/** Pipeline steps in order (spec 002 §10). */
export const ASSISTANT_STEPS: readonly AssistantStep[] = ['context', 'model', 'changeset'];
/** Requests in progress are polled every 2 seconds. */
export const ASSISTANT_POLL_MS = 2_000;
/** Longest instruction the server accepts. */
export const MESSAGE_MAX_LENGTH = 2_000;
/** How many of the user's latest requests the panel lists. */
export const ASSISTANT_LIST_LIMIT = 20;

export const assistantKeys = {
  all: ['assistant'] as const,
  list: (ontologyId: string) => [...assistantKeys.all, 'list', ontologyId] as const,
  request: (id: string) => [...assistantKeys.all, 'request', id] as const,
};

export function isActive(request: Pick<AssistantRequest, 'status'>): boolean {
  return request.status === 'queued' || request.status === 'running';
}

/** Length as the server counts it: characters (code points) of the trimmed text. */
export function messageLength(message: string): number {
  return Array.from(message.trim()).length;
}

/** The user's latest requests about an ontology, newest first. */
export function useAssistantRequests(ontologyId: string) {
  return useQuery({
    queryKey: assistantKeys.list(ontologyId),
    queryFn: () =>
      unwrap(
        api.GET('/api/ontologies/{id}/assistant/requests', {
          params: { path: { id: ontologyId }, query: { limit: ASSISTANT_LIST_LIMIT } },
        }),
      ),
  });
}

export function createAssistantRequest(ontologyId: string, body: AssistantRequestCreate): Promise<AssistantRequest> {
  return unwrap(api.POST('/api/ontologies/{id}/assistant/requests', { params: { path: { id: ontologyId } }, body }));
}

/**
 * Puts a new or updated request into the cached list, newest first. A list request already under
 * way may answer without it, so callers that add a request refetch the list as well.
 */
export function storeRequest(queryClient: QueryClient, request: AssistantRequest): void {
  queryClient.setQueryData<AssistantRequest[]>(assistantKeys.list(request.ontologyId), (current) => {
    if (!current) return [request];
    const known = current.some((existing) => existing.id === request.id);
    return known ? current.map((existing) => (existing.id === request.id ? request : existing)) : [request, ...current];
  });
}

function finished(queryClient: QueryClient, request: AssistantRequest): void {
  storeRequest(queryClient, request);
  if (!request.changeSetId) return;
  // A new change set waits for review: lists and counters elsewhere are out of date.
  void queryClient.invalidateQueries({ queryKey: changeSetKeys.list(request.ontologyId) });
  void queryClient.invalidateQueries({ queryKey: ontologyKeys.list() });
  void queryClient.invalidateQueries({ queryKey: ['workbench'] });
}

export function stopsPolling(error: unknown): boolean {
  // A 4xx (e.g. `assistant.not_found`) will not change by asking again; network and 5xx may.
  return isApiError(error) && error.status >= 400 && error.status < 500;
}

/**
 * One request, polled while it is queued or running; the list learns the outcome. `onSettled` hears
 * when a request seen in progress ends, `onLost` when polling stops on an error that will not pass.
 */
export function useAssistantRequest(
  request: AssistantRequest,
  onSettled?: (request: AssistantRequest) => void,
  onLost?: () => void,
) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: assistantKeys.request(request.id),
    queryFn: async () => {
      let next: AssistantRequest;
      try {
        next = await unwrap(api.GET('/api/assistant/requests/{id}', { params: { path: { id: request.id } } }));
      } catch (error) {
        if (stopsPolling(error)) onLost?.();
        throw error;
      }
      if (!isActive(next)) {
        finished(queryClient, next);
        onSettled?.(next);
      }
      return next;
    },
    initialData: request,
    enabled: isActive(request),
    refetchInterval: (query) => {
      if (stopsPolling(query.state.error)) return false;
      return isActive(query.state.data ?? request) ? ASSISTANT_POLL_MS : false;
    },
  });
}
