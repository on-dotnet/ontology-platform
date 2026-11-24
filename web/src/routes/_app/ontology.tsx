import { createFileRoute, useNavigate } from '@tanstack/react-router';

import { OntologyPage, type OntologyView } from '@/features/ontology/ontology-page';
import { validateOntologySearch, type OntologySearch } from '@/lib/search';

interface OntologyRouteSearch extends OntologySearch {
  /** Graph is the default view and is left out of the URL. */
  view?: Exclude<OntologyView, 'graph'>;
}

export const Route = createFileRoute('/_app/ontology')({
  validateSearch: (search: Record<string, unknown>): OntologyRouteSearch => {
    const { view: _view, ...rest } = validateOntologySearch(search) as OntologySearch & { view?: unknown };
    const known: Pick<OntologyRouteSearch, 'view'> = search.view === 'list' || search.view === 'turtle' ? { view: search.view } : {};
    return Object.assign({}, rest, known);
  },
  component: OntologyRoute,
});

function OntologyRoute() {
  const { ontology, view } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <OntologyPage
      ontologyId={ontology}
      view={view ?? 'graph'}
      onOntologyChange={(id) => void navigate({ search: (previous) => ({ ...previous, ontology: id }) })}
      onViewChange={(next: OntologyView) =>
        void navigate({
          search: (previous) => {
            const { view: _view, ...rest } = previous;
            return next === 'graph' ? rest : { ...rest, view: next };
          },
        })
      }
    />
  );
}
