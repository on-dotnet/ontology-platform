import { useTranslation } from 'react-i18next';

import { BrandMark } from '@/components/layout/brand';
import { LanguageMenu, ThemeMenu } from '@/components/layout/preference-menus';
import { Card } from '@/components/ui/card';
import { useDocumentTitle } from '@/lib/use-document-title';

import type { UserInfo } from './api';
import { LoginForm } from './login-form';

/** The platform's identity center: same tokens and components as the app (architecture §9). */
export function LoginPage({ onSuccess }: { onSuccess: (user: UserInfo) => void | Promise<void> }) {
  const { t } = useTranslation();
  useDocumentTitle(t('login.title'));

  return (
    <div className="relative isolate min-h-dvh overflow-hidden bg-background text-foreground">
      <div aria-hidden className="auth-backdrop pointer-events-none absolute inset-0 -z-10" />
      <div aria-hidden className="auth-grid pointer-events-none absolute inset-0 -z-10" />

      <header className="absolute right-4 top-4 flex items-center gap-1 sm:right-6 sm:top-6">
        <LanguageMenu />
        <ThemeMenu />
      </header>

      <main className="flex min-h-dvh items-center justify-center px-4 py-16">
        <div className="w-full max-w-[26rem]">
          <div className="mb-8 flex flex-col items-center gap-4 text-center">
            <BrandMark className="size-12 drop-shadow-sm" />
            <div>
              <p className="text-xl font-semibold tracking-tight text-foreground">{t('app.name')}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{t('app.authCenter')}</p>
            </div>
          </div>

          <Card className="p-6 shadow-popover sm:p-8 dark:shadow-none">
            <div className="mb-6">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t('login.title')}</h1>
              <p className="mt-1 text-sm text-muted-foreground">{t('login.subtitle')}</p>
            </div>
            <LoginForm onSuccess={onSuccess} />
          </Card>

          <p className="mt-6 text-center text-xs text-muted-foreground">{t('login.help')}</p>
        </div>
      </main>
    </div>
  );
}
