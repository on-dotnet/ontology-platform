import { createFileRoute, useNavigate } from '@tanstack/react-router';

import { DocumentsPage } from '@/features/documents/documents-page';
import { validateOntologySearch } from '@/lib/search';

export const Route = createFileRoute('/_app/documents')({
  validateSearch: validateOntologySearch,
  component: DocumentsRoute,
});

function DocumentsRoute() {
  const { ontology } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <DocumentsPage
      ontologyId={ontology}
      onOntologyChange={(id) => void navigate({ search: (previous) => ({ ...previous, ontology: id }) })}
    />
  );
}
