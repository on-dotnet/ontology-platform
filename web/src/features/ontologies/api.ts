import { keepPreviousData, queryOptions, useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';

export type OntologySummary = components['schemas']['OntologySummary'];
export type OntologyCreate = components['schemas']['OntologyCreate'];
export type Element = components['schemas']['Element'];
export type ElementDetail = components['schemas']['ElementDetail'];
export type ElementKind = Element['kind'];
export type Datatype = NonNullable<Element['datatype']>;
export type Synonym = Element['synonyms'][number];
export type Evidence = components['schemas']['Evidence'];
export type Graph = components['schemas']['Graph'];

export const ELEMENT_KINDS: readonly ElementKind[] = ['entity_type', 'relation_type', 'property'];
export const DATATYPES: readonly Datatype[] = ['string', 'integer', 'decimal', 'boolean', 'date', 'dateTime'];

export const ontologyKeys = {
  all: ['ontologies'] as const,
  list: () => [...ontologyKeys.all, 'list'] as const,
  elements: (id: string, filter: ElementFilter = {}) => [...ontologyKeys.all, id, 'elements', filter] as const,
  element: (id: string, elementId: string) => [...ontologyKeys.all, id, 'element', elementId] as const,
  graph: (id: string) => [...ontologyKeys.all, id, 'graph'] as const,
};

export function ontologiesQueryOptions() {
  return queryOptions({
    queryKey: ontologyKeys.list(),
    queryFn: () => unwrap(api.GET('/api/ontologies')),
  });
}

export function useOntologies() {
  return useQuery(ontologiesQueryOptions());
}

export function createOntology(body: OntologyCreate): Promise<OntologySummary> {
  return unwrap(api.POST('/api/ontologies', { body }));
}

export interface ElementFilter {
  kind?: ElementKind;
  q?: string;
}

export function useElements(ontologyId: string | undefined, filter: ElementFilter = {}) {
  return useQuery({
    queryKey: ontologyKeys.elements(ontologyId ?? '', filter),
    queryFn: () =>
      unwrap(
        api.GET('/api/ontologies/{id}/elements', {
          params: { path: { id: ontologyId ?? '' }, query: { kind: filter.kind, q: filter.q || undefined } },
        }),
      ),
    enabled: Boolean(ontologyId),
    // Keep the previous rows on screen while a new filter loads.
    placeholderData: keepPreviousData,
  });
}

export function useElementDetail(ontologyId: string, elementId: string | undefined) {
  return useQuery({
    queryKey: ontologyKeys.element(ontologyId, elementId ?? ''),
    queryFn: () =>
      unwrap(api.GET('/api/ontologies/{id}/elements/{elementId}', { params: { path: { id: ontologyId, elementId: elementId ?? '' } } })),
    enabled: Boolean(elementId),
  });
}

export function useGraph(ontologyId: string) {
  return useQuery({
    queryKey: ontologyKeys.graph(ontologyId),
    queryFn: () => unwrap(api.GET('/api/ontologies/{id}/graph', { params: { path: { id: ontologyId } } })),
  });
}

export function exportOntologyTurtle(ontologyId: string): Promise<string> {
  return unwrap(
    api.GET('/api/ontologies/{id}/export', {
      params: { path: { id: ontologyId }, query: { format: 'turtle' } },
      parseAs: 'text',
    }),
  );
}

/** Display name of an element in the current language: the English label when available in English. */
export function elementLabel(element: Pick<Element, 'labelZh' | 'labelEn'>, language: string): string {
  return language.startsWith('en') && element.labelEn ? element.labelEn : element.labelZh;
}
