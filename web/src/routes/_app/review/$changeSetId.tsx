import { createFileRoute } from '@tanstack/react-router';

import { ReviewDetailPage } from '@/features/review/review-detail-page';

export const Route = createFileRoute('/_app/review/$changeSetId')({
  component: ReviewDetailRoute,
});

function ReviewDetailRoute() {
  const { changeSetId } = Route.useParams();
  // Keyed so switching between change sets starts with fresh selection and dialogs.
  return <ReviewDetailPage key={changeSetId} changeSetId={changeSetId} />;
}
