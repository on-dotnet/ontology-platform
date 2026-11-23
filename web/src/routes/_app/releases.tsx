import { createFileRoute, useNavigate } from '@tanstack/react-router';

import { ReleasesPage } from '@/features/releases/releases-page';
import { validateOntologySearch } from '@/lib/search';

export const Route = createFileRoute('/_app/releases')({
  validateSearch: validateOntologySearch,
  component: ReleasesRoute,
});

function ReleasesRoute() {
  const { ontology } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <ReleasesPage
      ontologyId={ontology}
      onOntologyChange={(id) => void navigate({ search: (previous) => ({ ...previous, ontology: id }) })}
    />
  );
}
