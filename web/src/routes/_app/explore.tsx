import { createFileRoute } from '@tanstack/react-router';
import { Compass } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/explore')({
  component: () => <ComingSoonPage section="explore" icon={Compass} tone="secondary" />,
});
