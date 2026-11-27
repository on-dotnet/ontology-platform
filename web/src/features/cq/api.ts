import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { components } from '@/api/schema';

export type Question = components['schemas']['CompetencyQuestion'];
export type Check = components['schemas']['CqCheck'];
export type Create = components['schemas']['CompetencyQuestionCreate'];
type Patch = components['schemas']['CompetencyQuestionPatch'];

const collection = '/api/ontologies/{id}/competency-questions';
const params = (id: string) => ({ path: { id } });
export const listKey = (id: string) => ['cq', id, 'list'] as const;

export function useQuestions(id: string | undefined, poll = false) {
  return useQuery({
    queryKey: listKey(id ?? ''),
    enabled: Boolean(id),
    staleTime: 0,
    queryFn: async ({ signal }) => {
      const request = api.GET(collection, { params: params(id!), signal });
      const { items } = await unwrap(request);
      const header = (await request).response.headers.get('X-Cq-Check-Running');
      return { items: items.toSorted((a, b) => a.position - b.position), running: header === null ? null : header === 'true' };
    },
    refetchInterval: ({ state: { data } }) => poll && (data?.running || data?.items.some((q) => q.lastCheck?.result === 'pending')) ? 2000 : false,
  });
}

export function useCoverage(id: string, releaseId: string | null, items: Question[] | undefined) {
  // A new terminal check has a new plan. A new release can invalidate an existing plan.
  const plans = items?.flatMap(({ lastCheck }) => lastCheck && lastCheck.result !== 'pending' ? [lastCheck.id] : []);
  return useQuery({
    queryKey: ['cq', id, 'coverage', releaseId, plans],
    enabled: Boolean(items?.length),
    queryFn: ({ signal }) => unwrap(api.GET('/api/ontologies/{id}/competency-questions/coverage', { params: params(id), signal })),
  });
}

export function createQuestion(id: string, body: Create) {
  return unwrap(api.POST(collection, { params: params(id), body }));
}

export function patchQuestion(id: string, body: Patch) {
  return unwrap(api.PATCH('/api/competency-questions/{id}', { params: params(id), body }));
}

export function archiveQuestion({ id, revision }: Question) {
  return unwrap(api.POST('/api/competency-questions/{id}/archive', { params: params(id), body: { revision } }));
}

export function checkQuestion(id: string) {
  return unwrap(api.POST('/api/competency-questions/{id}/check', { params: params(id) }));
}

export function checkAll(id: string) {
  return unwrap(api.POST('/api/ontologies/{id}/competency-questions/check', { params: params(id) }));
}

export async function importQuestions(id: string, file: File) {
  if (file.size > 64 * 1024) throw new ApiError({ status: 422, code: 'cq.invalid_import' });
  const toml = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    const readError = () => new ApiError({ status: 422, code: 'cq.invalid_import' });
    reader.onerror = () => reject(reader.error ?? readError());
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result);
      else reject(readError());
    };
    reader.readAsText(file, 'utf-8');
  });
  return unwrap(api.POST('/api/ontologies/{id}/competency-questions/import', {
    params: params(id), headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    body: toml, bodySerializer: () => toml,
  }));
}
