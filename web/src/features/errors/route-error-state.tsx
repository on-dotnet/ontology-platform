import { useRouter, type ErrorComponentProps } from '@tanstack/react-router';

import { ErrorState } from '@/components/states/error-state';

/** Default error view for a route: rendered inside the shell, with retry. */
export function RouteErrorState({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <ErrorState
      error={error}
      onRetry={() => {
        reset();
        void router.invalidate();
      }}
    />
  );
}
