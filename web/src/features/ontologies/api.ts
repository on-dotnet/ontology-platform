import { keepPreviousData, queryOptions, useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components, operations } from '@/api/schema';

export type OntologySummary = components['schemas']['OntologySummary'];
export type OntologyCreate = components['schemas']['OntologyCreate'];
export type Element = components['schemas']['Element'];
export type ElementDetail = components['schemas']['ElementDetail'];
export type ElementKind = Element['kind'];
export type Datatype = NonNullable<Element['datatype']>;
export type Synonym = Element['synonyms'][number];
export type Evidence = components['schemas']['Evidence'];
export type Graph = components['schemas']['Graph'];
export type ConstraintRule = components['schemas']['ConstraintRule'];
export type ConstraintRuleFields = components['schemas']['ConstraintRuleFields'];
export type RdfValue = components['schemas']['RdfValue'];
export type LangText = components['schemas']['LangText'];
export type ImportResult = components['schemas']['ImportResult'];
export type ImportWarning = components['schemas']['ImportWarning'];
export type EditItem = components['schemas']['EditItem'];
export type EditRequest = components['schemas']['EditRequest'];
export type EditResult = components['schemas']['EditResult'];
export type ElementFields = components['schemas']['ElementFields'];
export type Impact = components['schemas']['Impact'];
export type ElementRef = components['schemas']['ElementRef'];
export type PlatformSettings = components['schemas']['PlatformSettings'];
export type ElementStatusFilter = NonNullable<
  NonNullable<operations['list_elements_api_ontologies__id__elements_get']['parameters']['query']>['status']
>;

export const ELEMENT_KINDS: readonly ElementKind[] = ['entity_type', 'relation_type', 'property', 'constraint', 'axiom'];
export const DATATYPES: readonly Datatype[] = ['string', 'integer', 'decimal', 'boolean', 'date', 'dateTime'];

export const ontologyKeys = {
  all: ['ontologies'] as const,
  list: () => [...ontologyKeys.all, 'list'] as const,
  elements: (id: string, filter: ElementFilter = {}) => [...ontologyKeys.all, id, 'elements', filter] as const,
  element: (id: string, elementId: string) => [...ontologyKeys.all, id, 'element', elementId] as const,
  graph: (id: string) => [...ontologyKeys.all, id, 'graph'] as const,
  impact: (id: string, elementId: string) => [...ontologyKeys.all, id, 'impact', elementId] as const,
  turtle: (id: string) => [...ontologyKeys.all, id, 'turtle'] as const,
};

export const platformSettingsKey = ['platform-settings'] as const;

/** Settings every page may need: the review mode. */
export function usePlatformSettings() {
  return useQuery({
    queryKey: platformSettingsKey,
    queryFn: () => unwrap(api.GET('/api/settings/platform')),
    staleTime: Infinity,
  });
}

/**
 * Whether the user's manual edits take effect on saving: reviewers and admins in single review
 * mode merge their own changes at once; everyone else submits them for review. False while the
 * settings load, so that nothing claims to apply what may go to review.
 */
export function useAppliesEdits(canReview: boolean): boolean {
  const settings = usePlatformSettings();
  return canReview && settings.data?.reviewMode === 'single';
}

/**
 * Saves changes made by hand as a manual change set; with `apply` and the right to review one's
 * own changes it is merged at once (409 `element.stale` when a target changed meanwhile).
 */
export function saveEdits(ontologyId: string, body: EditRequest): Promise<EditResult> {
  return unwrap(api.POST('/api/ontologies/{id}/edits', { params: { path: { id: ontologyId } }, body }));
}

/** What refers to an element; deleting it takes these along. */
export function useImpact(ontologyId: string, elementId: string | undefined) {
  return useQuery({
    queryKey: ontologyKeys.impact(ontologyId, elementId ?? ''),
    queryFn: () =>
      unwrap(api.GET('/api/ontologies/{id}/elements/{elementId}/impact', { params: { path: { id: ontologyId, elementId: elementId ?? '' } } })),
    enabled: Boolean(elementId),
  });
}

/** Expert mode: the edited Turtle of the whole working version; the differences go to review. */
export function saveTurtle(ontologyId: string, turtle: string): Promise<ImportResult> {
  return unwrap(api.POST('/api/ontologies/{id}/turtle', { params: { path: { id: ontologyId } }, body: { turtle } }));
}

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

/** Largest OWL file the server accepts (`import.too_large`). */
export const MAX_IMPORT_MB = 5;
/** File types offered by the picker; the server detects the format from the content. */
export const IMPORT_ACCEPT = '.ttl,.owl,.rdf,.xml';

/** Creates an ontology from a Turtle or RDF/XML file; its content arrives as an import change set. */
export function importOntology(file: File, name?: string): Promise<ImportResult> {
  return unwrap(
    api.POST('/api/ontologies/import', {
      // The generated type models the binary part as a string; the serializer sends the File itself.
      body: { file: file as unknown as string, ...(name ? { name } : {}) },
      bodySerializer: () => {
        const form = new FormData();
        form.append('file', file, file.name);
        if (name) form.append('name', name);
        return form;
      },
    }),
  );
}

/** Compares a file with the working version; the differences become an import change set (none without differences). */
export function importIntoOntology(ontologyId: string, file: File): Promise<ImportResult> {
  return unwrap(
    api.POST('/api/ontologies/{id}/import', {
      params: { path: { id: ontologyId } },
      body: { file: file as unknown as string },
      bodySerializer: () => {
        const form = new FormData();
        form.append('file', file, file.name);
        return form;
      },
    }),
  );
}

export interface ElementFilter {
  kind?: ElementKind;
  q?: string;
  /** Active elements by default; deleted ones with `deprecated` or `all`. */
  status?: ElementStatusFilter;
}

export function useElements(ontologyId: string | undefined, filter: ElementFilter = {}) {
  return useQuery({
    queryKey: ontologyKeys.elements(ontologyId ?? '', filter),
    queryFn: () =>
      unwrap(
        api.GET('/api/ontologies/{id}/elements', {
          params: { path: { id: ontologyId ?? '' }, query: { kind: filter.kind, q: filter.q || undefined, status: filter.status } },
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

/** The working version as Turtle: the expert mode's text and the prefixes axioms may use. */
export function useOntologyTurtle(ontologyId: string) {
  return useQuery({
    queryKey: ontologyKeys.turtle(ontologyId),
    queryFn: () => exportOntologyTurtle(ontologyId),
  });
}

export interface TurtlePrefix {
  /** Empty for the default prefix `:`. */
  name: string;
  iri: string;
}

const PREFIX_LINE = /^\s*@prefix\s+([A-Za-z][\w.-]*)?:\s*<([^>]*)>\s*\.\s*$/;

/** The `@prefix` declarations of a Turtle text, in order. */
export function turtlePrefixes(turtle: string): TurtlePrefix[] {
  return turtle.split('\n').flatMap((line) => {
    const match = PREFIX_LINE.exec(line);
    return match ? [{ name: match[1] ?? '', iri: match[2] ?? '' }] : [];
  });
}

/** The names an element or change item may carry; any of them can be missing (imports, axioms). */
export interface Names {
  labelZh?: string | null;
  labelEn?: string | null;
  localName?: string | null;
}

/**
 * Display name in the current language: the label of that language, then the other label, then the
 * local name; empty when there is none (axioms).
 */
export function displayName(names: Names, language: string): string {
  const labels = language.startsWith('en') ? [names.labelEn, names.labelZh] : [names.labelZh, names.labelEn];
  return [...labels, names.localName].find((value): value is string => Boolean(value?.trim())) ?? '';
}

/** First line of a Turtle fragment, shortened to `max` characters, to name an axiom. */
export function turtleSummary(turtle: string | null | undefined, max = 80): string {
  const line = (turtle ?? '').split('\n').map((part) => part.trim()).find(Boolean) ?? '';
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

/** Display name of an element; axioms, which have no names, are named by their Turtle. */
export function elementName(element: Names & { turtle?: string | null }, language: string): string {
  return displayName(element, language) || turtleSummary(element.turtle);
}
