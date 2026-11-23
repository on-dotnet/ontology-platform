import { createFileRoute } from '@tanstack/react-router';
import { FileText } from 'lucide-react';

import { ComingSoonPage } from '@/features/placeholder/coming-soon-page';

export const Route = createFileRoute('/_app/documents')({
  component: () => <ComingSoonPage section="documents" icon={FileText} tone="primary" />,
});
