import { createFileRoute } from '@tanstack/react-router';
import { Network } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/ontology')({
  component: () => <ComingSoonPage section="ontology" icon={Network} tone="info" />,
});
