import { createFileRoute } from '@tanstack/react-router';
import { ClipboardCheck } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/review')({
  component: () => <ComingSoonPage section="review" icon={ClipboardCheck} tone="warning" />,
});
