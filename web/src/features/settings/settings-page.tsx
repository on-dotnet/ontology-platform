import { SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { InfoTip } from '@/components/feedback/hint-tip';
import { PageHeader } from '@/components/layout/page-header';
import { Avatar } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/features/auth/api';

import { LanguageSelector, ThemeSelector } from './preference-controls';

export function SettingsPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();

  return (
    <>
      <PageHeader title={t('nav.settings')} info={t('settings.info')} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t('settings.accountTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            {user ? (
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
                <Avatar name={user.displayName || user.username} className="size-14 text-lg" />
                <dl className="grid flex-1 grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
                  <dt className="text-muted-foreground">{t('settings.displayName')}</dt>
                  <dd className="font-medium text-foreground">{user.displayName || user.username}</dd>
                  <dt className="text-muted-foreground">{t('settings.username')}</dt>
                  <dd className="font-medium text-foreground">{user.username}</dd>
                  <dt className="text-muted-foreground">{t('settings.role')}</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    <Badge tone="primary">{t(`user.roles.${user.role}`)}</Badge>
                  </dd>
                </dl>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-1">
            <CardTitle>{t('settings.preferencesTitle')}</CardTitle>
            <InfoTip label={t('common.aboutPage', { title: t('settings.preferencesTitle') })}>
              {t('settings.preferencesInfo')}
            </InfoTip>
          </CardHeader>
          <CardContent className="space-y-5">
            <LanguageSelector />
            <ThemeSelector />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="flex items-center gap-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary-soft text-secondary-strong">
              <SlidersHorizontal className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-foreground">{t('settings.platformTitle')}</h2>
                <Badge tone="secondary">{t('common.comingSoon')}</Badge>
              </div>
              <p className="mt-0.5 text-sm text-muted-foreground">{t('settings.platformDescription')}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
