/** A non-empty string search value, or undefined. */
export function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

export interface OntologySearch {
  /** Selected ontology id; the first ontology is used when absent or unknown. */
  ontology?: string;
}

/**
 * Validates `?ontology=`. Other parameters are kept so shared links and redirects survive unchanged;
 * pages only read the keys they declare.
 */
export function validateOntologySearch(search: Record<string, unknown>): OntologySearch {
  const { ontology, ...rest } = search;
  const id = optionalString(ontology);
  const known: OntologySearch = id ? { ontology: id } : {};
  return Object.assign({}, rest, known);
}
