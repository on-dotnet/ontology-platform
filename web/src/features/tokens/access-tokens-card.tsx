import { KeyRound } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { EmptyState } from '@/components/states/empty-state';
import { LoadingState } from '@/components/states/loading-state';
import { QueryState } from '@/components/states/query-state';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SegmentedControl } from '@/components/ui/segmented-control';
import { useCurrentUser, type UserInfo } from '@/features/auth/api';

import { useAccessTokens, type OwnerView } from './api';
import { CreateTokenDialog } from './create-token-dialog';
import { TokenTable } from './token-table';

export function AccessTokensCard() {
  const user = useCurrentUser();
  return (
    <Card className="min-w-0 lg:col-span-2">
      {user
        ? <TokenManager key={user.id} user={user} />
        : <CardContent><LoadingState /></CardContent>}
    </Card>
  );
}

function TokenManager({ user }: { user: UserInfo }) {
  const { t } = useTranslation();
  const [selectedOwner, setOwner] = useState<OwnerView>('me');
  const owner = user.role === 'admin' ? selectedOwner : 'me';
  const query = useAccessTokens(user.id, owner);
  return (
    <>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <KeyRound className="size-5 text-primary-strong" aria-hidden />
          <CardTitle>{t('tokens.title')}</CardTitle>
          <InfoTip label={t('tokens.about')}>{t('tokens.description')}</InfoTip>
        </div>
        <CreateTokenDialog />
      </CardHeader>
      <CardContent className="space-y-4">
        {user.role === 'admin' ? (
          <SegmentedControl<OwnerView>
            legend={t('tokens.view.label')} hideLegend value={owner} onValueChange={setOwner}
            options={[{ value: 'me', label: t('tokens.view.me') }, { value: 'all', label: t('tokens.view.all') }]}
          />
        ) : null}
        <QueryState query={query} requiredRole={owner === 'all' ? 'admin' : 'viewer'}>
          {(tokens) => tokens.length
            ? <TokenTable key={owner} tokens={tokens} showOwner={owner === 'all'} />
            : <EmptyState icon={KeyRound} title={t('tokens.empty')} description={t('tokens.emptyDescription')} headingLevel="h3" />}
        </QueryState>
      </CardContent>
    </>
  );
}
