import { createFileRoute } from '@tanstack/react-router';
import { History } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/releases')({
  component: () => <ComingSoonPage section="releases" icon={History} tone="primary" />,
});
