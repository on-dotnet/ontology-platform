import { Activity, ClipboardCheck, Database, Network, Sparkles, type LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { useCurrentUser } from '@/features/auth/api';
import { cn } from '@/lib/cn';

type Tone = 'warning' | 'primary' | 'success' | 'info';

const toneStyles: Record<Tone, { card: string; text: string }> = {
  warning: { card: 'bg-warning-soft', text: 'text-warning-strong' },
  primary: { card: 'bg-primary-soft', text: 'text-primary-strong' },
  success: { card: 'bg-success-soft', text: 'text-success-strong' },
  info: { card: 'bg-info-soft', text: 'text-info-strong' },
};

const overview: readonly { key: string; icon: LucideIcon; tone: Tone }[] = [
  { key: 'pending', icon: ClipboardCheck, tone: 'warning' },
  { key: 'ontology', icon: Network, tone: 'primary' },
  { key: 'data', icon: Database, tone: 'success' },
  { key: 'activity', icon: Activity, tone: 'info' },
];

function greetingKey(hour: number): string {
  if (hour < 12) return 'workbench.greetingMorning';
  if (hour < 18) return 'workbench.greetingAfternoon';
  return 'workbench.greetingEvening';
}

export function WorkbenchPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const [hour] = useState(() => new Date().getHours());
  const name = user?.displayName || user?.username || '';

  return (
    <>
      <PageHeader title={t(greetingKey(hour), { name })} documentTitle={t('workbench.title')} info={t('workbench.info')} />

      <section
        aria-labelledby="ai-intake-title"
        className="relative overflow-hidden rounded-xl border border-border bg-card shadow-card"
      >
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-linear-to-r from-info-soft via-primary-soft to-transparent" />
        <Sparkles aria-hidden className="pointer-events-none absolute -right-6 -top-8 size-44 text-info/10" strokeWidth={1.25} />
        <div className="relative flex flex-col gap-5 p-6 md:flex-row md:items-center md:gap-6 md:p-8">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-info text-primary-foreground shadow-sm">
            <Sparkles className="size-7" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="ai-intake-title" className="text-xl font-semibold text-foreground">
                {t('workbench.aiCardTitle')}
              </h2>
              <Badge tone="info">{t('common.comingSoon')}</Badge>
            </div>
            <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{t('workbench.aiCardDescription')}</p>
          </div>
        </div>
      </section>

      {/* Each card says what it will show once available; it never claims anything about current data. */}
      <section aria-label={t('workbench.sectionsLabel')} className="mt-6 grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {overview.map(({ key, icon: Icon, tone }) => (
          <div key={key} className={cn('flex flex-col rounded-xl p-5', toneStyles[tone].card)}>
            <div className="flex items-center gap-3">
              <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg bg-card shadow-sm', toneStyles[tone].text)}>
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className={cn('min-w-0 flex-1 text-base font-semibold', toneStyles[tone].text)}>{t(`workbench.${key}Title`)}</h3>
            </div>
            <p className="mt-4 flex-1 text-sm text-muted-foreground">{t(`workbench.${key}Description`)}</p>
            <Badge tone={tone} className="mt-4 self-start bg-card">
              {t('common.comingSoon')}
            </Badge>
          </div>
        ))}
      </section>
    </>
  );
}
