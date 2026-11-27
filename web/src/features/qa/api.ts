import { useIsMutating, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { stopsPolling } from '@/features/assistant/api';

export type Question = components['schemas']['QaQuestion'];
type QuestionList = components['schemas']['QaQuestionList'];
type Create = components['schemas']['QaQuestionCreate'];

const listKey = (ontologyId: string) => ['qa', 'recent', ontologyId] as const;
const detailKey = (id: string | undefined) => ['qa', 'question', id] as const;
export const isActive = (question?: Question) => question?.status === 'queued' || question?.status === 'running';
export const isGapActive = (proposal?: Question['gapProposal']) => proposal?.status === 'queued' || proposal?.status === 'running';

function needsPolling(question?: Question) {
  return isActive(question) || isGapActive(question?.gapProposal);
}

export function useRecentQuestions(id: string) {
  return useQuery({
    queryKey: listKey(id),
    queryFn: ({ signal }) => unwrap(api.GET('/api/ontologies/{id}/qa/questions', {
      params: { path: { id }, query: { askedBy: 'me' } }, signal,
    })),
    staleTime: 0,
    retry: false,
  });
}

export function useQuestion(id: string | undefined, summary: Question | undefined) {
  const client = useQueryClient();
  return useQuery({
    queryKey: detailKey(id),
    enabled: !!id,
    // Active questions and gap proposals can be shown from a summary while detail loads.
    initialData: needsPolling(summary) ? summary : undefined,
    initialDataUpdatedAt: 0,
    // Reopening a question must pick up proposals started in another session.
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const next = await unwrap(api.GET('/api/qa/questions/{id}', { params: { path: { id: id! } }, signal }));
      if (!needsPolling(next) && (needsPolling(client.getQueryData<Question>(detailKey(id))) || needsPolling(summary))) {
        void client.invalidateQueries({ queryKey: listKey(next.ontologyId) });
      }
      return next;
    },
    refetchInterval: ({ state }) => !stopsPolling(state.error) && needsPolling(state.data) ? 2000 : false,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export function useGapProposal(id: string) {
  const client = useQueryClient();
  const mutationKey = ['qa', 'gap-proposal', id] as const;
  const pending = useIsMutating({ mutationKey }) > 0;
  const mutation = useMutation({
    mutationKey,
    mutationFn: () => unwrap(api.POST('/api/qa/questions/{id}/gap-proposal', { params: { path: { id } } })),
    onSuccess: async (question) => {
      const queryKey = detailKey(id);
      // A detail fetch started before this POST may still have the old question.
      await client.cancelQueries({ queryKey, exact: true });
      client.setQueryData<Question>(queryKey, (current) =>
        current?.gapProposal && !isGapActive(current.gapProposal) ? current : question);
    },
    onError: (error) => {
      // A lost response can still mean the server accepted the proposal.
      if (!stopsPolling(error)) return client.invalidateQueries({ queryKey: detailKey(id) });
    },
  });
  return {
    pending, error: mutation.error,
    submit: () => {
      if (!client.isMutating({ mutationKey }) && !client.getQueryData<Question>(detailKey(id))?.gapProposal) mutation.mutate();
    },
  };
}

function createQuestion(id: string, body: Create) {
  return unwrap(api.POST('/api/ontologies/{id}/qa/questions', { params: { path: { id } }, body }).then((result) => {
    // unwrap keeps problem extensions but discards headers. Resolve the deadline when the response arrives.
    const header = result.response.headers.get('Retry-After');
    if (result.response.status !== 429 || !header) return result;
    const retryAt = /^\d+$/.test(header) ? Date.now() + Number(header) * 1000 : Date.parse(header);
    return { ...result, error: { ...result.error, retryAt } };
  }));
}

export function useCreateQuestion(id: string, select: (id: string) => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Create) => createQuestion(id, body),
    onSuccess: (question) => {
      client.setQueryData(detailKey(question.id), question);
      client.setQueryData<QuestionList>(listKey(id), (list) => ({
        items: [{ ...question, evidence: null }, ...(list?.items ?? []).filter((q) => q.id !== question.id)],
        nextCursor: list?.nextCursor ?? null,
      }));
      select(question.id);
      void client.invalidateQueries({ queryKey: listKey(id) });
    },
  });
}
