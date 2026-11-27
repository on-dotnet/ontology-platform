import { createFileRoute, useNavigate } from '@tanstack/react-router';

import { ReviewMemoryPage } from '@/features/review-memory/review-memory-page';
import { optionalString, validateOntologySearch } from '@/lib/search';

const kinds = ['rejected', 'renamed', 'kept_apart'] as const;

export const Route = createFileRoute('/_app/review/memory')({
  validateSearch: (search: Record<string, unknown>) => {
    const { kind: rawKind, q: rawQ, entry: rawEntry, ...rest } = search;
    const kind = kinds.find((candidate) => candidate === rawKind);
    const q = optionalString(rawQ)?.slice(0, 100);
    const entry = optionalString(rawEntry);
    return { ...validateOntologySearch(rest), ...(kind ? { kind } : {}), ...(q ? { q } : {}), ...(entry ? { entry } : {}) };
  },
  component: MemoryRoute,
});

function MemoryRoute() {
  const { ontology, kind, q, entry } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return <ReviewMemoryPage ontologyId={ontology} kind={kind} q={q} entry={entry}
    onSearchChange={(change) => void navigate({ search: (previous) => ({ ...previous, ...change }), replace: true })} />;
}
