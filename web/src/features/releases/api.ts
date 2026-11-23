import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/schema';

export type ReleaseSummary = components['schemas']['ReleaseSummary'];
export type ReleaseCreate = components['schemas']['ReleaseCreate'];
export type ReleaseProblem = components['schemas']['ReleaseProblem'];

export const releaseKeys = {
  all: ['releases'] as const,
  list: (ontologyId: string) => [...releaseKeys.all, 'list', ontologyId] as const,
};

export function useReleases(ontologyId: string) {
  return useQuery({
    queryKey: releaseKeys.list(ontologyId),
    queryFn: () => unwrap(api.GET('/api/ontologies/{id}/releases', { params: { path: { id: ontologyId } } })),
  });
}

export function publishRelease(ontologyId: string, body: ReleaseCreate): Promise<ReleaseSummary> {
  return unwrap(api.POST('/api/ontologies/{id}/releases', { params: { path: { id: ontologyId } }, body }));
}

export function activateRelease(id: string): Promise<ReleaseSummary> {
  return unwrap(api.POST('/api/releases/{id}/activate', { params: { path: { id } } }));
}

export function exportReleaseTurtle(id: string): Promise<string> {
  return unwrap(api.GET('/api/releases/{id}/export', { params: { path: { id }, query: { format: 'turtle' } }, parseAs: 'text' }));
}

function isProblem(value: unknown): value is ReleaseProblem {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record.code === 'string' && (record.elementId === null || typeof record.elementId === 'string' || record.elementId === undefined);
}

/** The validation problems of a 422 `release.invalid`, or null for any other error. */
export function releaseProblems(error: unknown): ReleaseProblem[] | null {
  if (!isApiError(error) || error.code !== 'release.invalid') return null;
  const problems = error.body.problems;
  if (!Array.isArray(problems)) return [];
  return problems.filter(isProblem).map((problem) => ({ ...problem, elementId: problem.elementId ?? null }));
}
