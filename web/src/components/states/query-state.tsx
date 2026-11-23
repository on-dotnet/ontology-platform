import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { isForbidden } from '@/api/errors';
import type { Role } from '@/features/auth/api';

import { ErrorState } from './error-state';
import { ForbiddenState } from './forbidden-state';
import { LoadingState } from './loading-state';

interface QueryStateProps<T> {
  query: UseQueryResult<T>;
  /** Skeleton matching the final layout; a list skeleton by default. */
  loading?: ReactNode;
  errorTitle?: string;
  /** Role named in the "no access" state when the request is refused (403). */
  requiredRole?: Role;
  children: (data: T) => ReactNode;
}

/** Loading, error (with retry), no access, or the data (ui-guidelines §5). Empty states stay with the caller. */
export function QueryState<T>({ query, loading, errorTitle, requiredRole = 'viewer', children }: QueryStateProps<T>) {
  if (query.isPending) return <>{loading ?? <LoadingState />}</>;
  if (query.isError) {
    if (isForbidden(query.error)) return <ForbiddenState requiredRole={requiredRole} />;
    return <ErrorState error={query.error} title={errorTitle} onRetry={() => void query.refetch()} />;
  }
  return <>{children(query.data)}</>;
}
