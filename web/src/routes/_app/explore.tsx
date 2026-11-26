import { createFileRoute, redirect } from '@tanstack/react-router';

import { Tabs } from '@/components/ui/tabs';
import { ExplorePage, isExploreTab, type ExploreTab } from '@/features/explore/explore-page';

export const Route = createFileRoute('/_app/explore')({
  validateSearch: ({ tab, ...rest }: Record<string, unknown>): { tab?: ExploreTab } =>
    tab === undefined ? rest : { ...rest, tab: isExploreTab(tab) ? tab : 'objects' },
  beforeLoad: ({ location, search }) => {
    const raw = new URLSearchParams(location.searchStr).get('tab');
    if (raw !== null && !isExploreTab(raw)) {
      throw redirect({ to: '/explore', search: { ...search, tab: 'objects' }, replace: true });
    }
  },
  component: ExploreRoute,
});

function ExploreRoute() {
  const { tab = 'objects' } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <Tabs value={tab} onValueChange={(next) => {
      if (isExploreTab(next)) void navigate({ search: (previous) => ({ ...previous, tab: next }) });
    }}>
      <ExplorePage />
    </Tabs>
  );
}
