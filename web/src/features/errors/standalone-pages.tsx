import { Link, useRouter, type ErrorComponentProps } from '@tanstack/react-router';
import { Compass } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { BrandMark, BrandName } from '@/components/layout/brand';
import { EmptyState } from '@/components/states/empty-state';
import { ErrorState } from '@/components/states/error-state';
import { buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useDocumentTitle } from '@/lib/use-document-title';

function StandaloneLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-background px-4 py-16 text-foreground">
      <div className="mb-8 flex items-center gap-3">
        <BrandMark />
        <BrandName />
      </div>
      <div className="w-full max-w-lg">{children}</div>
    </div>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  useDocumentTitle(t('states.notFoundTitle'));
  return (
    <StandaloneLayout>
      <Card>
        <EmptyState
          icon={Compass}
          tone="secondary"
          headingLevel="h1"
          title={t('states.notFoundTitle')}
          description={t('states.notFoundDescription')}
          action={
            <Link to="/" className={buttonVariants({ variant: 'primary' })}>
              {t('common.backToWorkbench')}
            </Link>
          }
        />
      </Card>
    </StandaloneLayout>
  );
}

/** Shown when the session check itself fails (e.g. the API is unreachable). */
export function AppErrorPage({ error, reset }: ErrorComponentProps) {
  const { t } = useTranslation();
  const router = useRouter();
  useDocumentTitle(t('states.appErrorTitle'));
  return (
    <StandaloneLayout>
      <ErrorState
        error={error}
        title={t('states.appErrorTitle')}
        onRetry={() => {
          reset();
          void router.invalidate();
        }}
      />
    </StandaloneLayout>
  );
}

/** Skeleton of the app shell while the session is being checked; keeps the final layout. */
export function AppShellSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy className="flex h-dvh overflow-hidden bg-background">
      <span className="sr-only">{t('common.loading')}</span>
      <div className="hidden w-64 shrink-0 flex-col gap-3 border-r border-border bg-card p-4 lg:flex">
        <div className="mb-4 flex items-center gap-3 px-1 pt-2">
          <BrandMark />
          <Skeleton className="h-4 w-28" />
        </div>
        {[0, 1, 2, 3, 4, 5, 6].map((key) => (
          <Skeleton key={key} className="h-9 rounded-lg" />
        ))}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="ml-auto size-9 rounded-full" />
        </div>
        <div className="space-y-6 p-6">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-36 rounded-xl" />
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-32 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
