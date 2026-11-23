import { createFileRoute, useNavigate } from '@tanstack/react-router';

import { ReviewListPage } from '@/features/review/review-list-page';
import { validateOntologySearch } from '@/lib/search';

export const Route = createFileRoute('/_app/review/')({
  validateSearch: validateOntologySearch,
  component: ReviewRoute,
});

function ReviewRoute() {
  const { ontology } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <ReviewListPage
      ontologyId={ontology}
      onOntologyChange={(id) => void navigate({ search: (previous) => ({ ...previous, ontology: id }) })}
    />
  );
}
