import { useOntologies, type OntologySummary } from './api';

/**
 * The ontologies list and the one a page works on: the id from the URL when it exists,
 * otherwise the first ontology. `selected` is undefined while loading or when there is none.
 */
export function useSelectedOntology(requestedId: string | undefined) {
  const query = useOntologies();
  const ontologies: readonly OntologySummary[] | undefined = query.data;
  const selected = ontologies?.find((ontology) => ontology.id === requestedId) ?? ontologies?.[0];
  return { query, ontologies, selected };
}
