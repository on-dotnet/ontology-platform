import { Link, useNavigate } from '@tanstack/react-router';
import {
  Activity as ActivityIcon,
  ArrowRight,
  ClipboardCheck,
  FileText,
  History,
  Network,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/page-header';
import { ErrorState } from '@/components/states/error-state';
import { QueryState } from '@/components/states/query-state';
import { NativeSelect } from '@/components/ui/native-select';
import { RelativeTime } from '@/components/ui/relative-time';
import { Skeleton } from '@/components/ui/skeleton';
import { AiStatusNotice } from '@/features/ai/ai-status';
import { useCurrentUser } from '@/features/auth/api';
import { usePermissions } from '@/features/auth/permissions';
import { UploadDropZone, UploadProblems, useDocumentUpload } from '@/features/documents/upload';
import { useOntologies } from '@/features/ontologies/api';
import { lookupText } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

import { useWorkbenchSummary, type Activity } from './api';

type Tone = 'warning' | 'primary' | 'success' | 'info';

const toneStyles: Record<Tone, { card: string; text: string }> = {
  warning: { card: 'bg-warning-soft', text: 'text-warning-strong' },
  primary: { card: 'bg-primary-soft', text: 'text-primary-strong' },
  success: { card: 'bg-success-soft', text: 'text-success-strong' },
  info: { card: 'bg-info-soft', text: 'text-info-strong' },
};

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
      <AiIntakeCard />
      <Overview />
    </>
  );
}

/** "AI document analysis": drop or choose files; names the first ontology when there is none. */
function AiIntakeCard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { canUpload } = usePermissions();
  const ontologies = useOntologies();
  const targetId = useId();
  const [chosen, setChosen] = useState<string | null>(null);
  const list = ontologies.data;
  const target = list?.find((ontology) => ontology.id === chosen) ?? list?.[0];
  const upload = useDocumentUpload({
    ontologyId: target?.id,
    needsOntology: list?.length === 0,
    onUploaded: (ontologyId) => void navigate({ to: '/documents', search: { ontology: ontologyId } }),
  });

  let body: ReactNode;
  if (!canUpload) {
    body = <p className="text-sm text-muted-foreground">{t('workbench.uploadNeedsRole', { role: t('user.roles.editor') })}</p>;
  } else if (ontologies.isPending) {
    body = <Skeleton className="h-44 rounded-xl" />;
  } else if (ontologies.isError) {
    body = <ErrorState error={ontologies.error} onRetry={() => void ontologies.refetch()} />;
  } else {
    body = (
      <div className="space-y-3">
        {list && list.length > 1 && target ? (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={targetId} className="text-sm font-medium text-muted-foreground">
              {t('workbench.uploadTarget')}
            </label>
            <NativeSelect
              id={targetId}
              value={target.id}
              onChange={(event) => setChosen(event.target.value)}
              containerClassName="w-56 max-w-full"
              className="h-9"
            >
              {list.map((ontology) => (
                <option key={ontology.id} value={ontology.id}>
                  {ontology.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        ) : null}
        <UploadProblems problems={upload.problems} onDismiss={upload.dismissProblems} />
        <UploadDropZone onFiles={upload.submit} busy={upload.isUploading} primary />
      </div>
    );
  }

  return (
    <section aria-labelledby="ai-intake-title" className="relative overflow-hidden rounded-xl border border-border bg-card shadow-card">
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-linear-to-r from-info-soft via-primary-soft to-transparent" />
      <Sparkles aria-hidden className="pointer-events-none absolute -right-6 -top-8 size-44 text-info/10" strokeWidth={1.25} />
      <div className="relative grid gap-6 p-6 md:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:items-center">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-info text-primary-foreground shadow-sm">
            <Sparkles className="size-7" aria-hidden />
          </span>
          <div className="min-w-0 flex-1 space-y-3">
            <div>
              <h2 id="ai-intake-title" className="text-xl font-semibold text-foreground">
                {t('workbench.aiCardTitle')}
              </h2>
              <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{t('workbench.aiCardDescription')}</p>
            </div>
            <AiStatusNotice />
          </div>
        </div>
        {body}
        {upload.dialog}
      </div>
    </section>
  );
}

interface StatCardProps {
  icon: LucideIcon;
  tone: Tone;
  title: string;
  value: number;
  description: string;
  link: ReactNode;
}

function StatCard({ icon: Icon, tone, title, value, description, link }: StatCardProps) {
  return (
    <div className={cn('flex flex-col rounded-xl p-5', toneStyles[tone].card)}>
      <div className="flex items-center gap-3">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg bg-card shadow-sm', toneStyles[tone].text)}>
          <Icon className="size-5" aria-hidden />
        </span>
        <h3 className={cn('min-w-0 flex-1 text-base font-semibold', toneStyles[tone].text)}>{title}</h3>
      </div>
      <p className="mt-4 text-3xl font-semibold tabular-nums text-foreground">{value}</p>
      <p className="mt-1 flex-1 text-sm text-muted-foreground">{description}</p>
      <div className={cn('mt-4 text-sm font-medium', toneStyles[tone].text)}>{link}</div>
    </div>
  );
}

function CardLink({ to, children }: { to: '/review' | '/ontology' | '/documents'; children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1 rounded hover:underline">
      {children}
      <ArrowRight className="size-3.5" aria-hidden />
    </Link>
  );
}

function Overview() {
  const { t } = useTranslation();
  const query = useWorkbenchSummary();
  return (
    <section aria-label={t('workbench.sectionsLabel')} className="mt-6">
      <QueryState
        query={query}
        loading={
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4" role="status" aria-busy>
            <span className="sr-only">{t('common.loading')}</span>
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-48 rounded-xl" />
            ))}
          </div>
        }
      >
        {(summary) => (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              icon={ClipboardCheck}
              tone="warning"
              title={t('workbench.pendingTitle')}
              value={summary.pendingChangeSets}
              description={t('workbench.pendingDescription')}
              link={<CardLink to="/review">{t('workbench.pendingLink')}</CardLink>}
            />
            <StatCard
              icon={Network}
              tone="primary"
              title={t('workbench.ontologyTitle')}
              value={summary.entityTypes}
              description={t('workbench.ontologyDescription')}
              link={<CardLink to="/ontology">{t('workbench.ontologyLink')}</CardLink>}
            />
            <StatCard
              icon={FileText}
              tone="success"
              title={t('workbench.processingTitle')}
              value={summary.processingDocuments}
              description={t('workbench.processingDescription')}
              link={<CardLink to="/documents">{t('workbench.processingLink')}</CardLink>}
            />
            <ActivityCard activities={summary.recentActivity} />
          </div>
        )}
      </QueryState>
    </section>
  );
}

const activityIcons: Record<string, LucideIcon> = {
  ontology: Network,
  document: FileText,
  changeset: ClipboardCheck,
  release: History,
};

function ActivityCard({ activities }: { activities: readonly Activity[] }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col rounded-xl bg-info-soft p-5 sm:col-span-2 xl:col-span-1">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-card text-info-strong shadow-sm">
          <ActivityIcon className="size-5" aria-hidden />
        </span>
        <h3 className="min-w-0 flex-1 text-base font-semibold text-info-strong">{t('workbench.activityTitle')}</h3>
      </div>
      {activities.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">{t('workbench.activityEmpty')}</p>
      ) : (
        <ol className="mt-4 max-h-64 space-y-3 overflow-y-auto pr-1" aria-label={t('workbench.activityTitle')}>
          {activities.map((activity) => (
            <ActivityRow key={activity.id} activity={activity} />
          ))}
        </ol>
      )}
    </div>
  );
}

function ActivityRow({ activity }: { activity: Activity }) {
  const { t, i18n } = useTranslation();
  const domain = activity.action.split('.')[0] ?? '';
  const Icon = activityIcons[domain] ?? ActivityIcon;
  const text = lookupText(i18n, `activity.actions.${activity.action}`) ?? t('activity.actions.unknown');
  const actor = activity.actorName ?? t('activity.system');
  return (
    <li className="flex gap-2.5 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0 text-info-strong" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-foreground">
          <span className="font-medium">{actor}</span> {text}
        </p>
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <RelativeTime value={activity.occurredAt} />
          <ActivityTarget activity={activity} />
        </p>
      </div>
    </li>
  );
}

/** Link to what the activity concerns, when the platform has a page for it. */
function ActivityTarget({ activity }: { activity: Activity }) {
  const { t } = useTranslation();
  const className = 'rounded font-medium text-info-strong hover:underline';
  const { targetType, targetId } = activity;
  if (!targetType || !targetId) return null;
  if (targetType === 'change_set') {
    return (
      <Link to="/review/$changeSetId" params={{ changeSetId: targetId }} className={className}>
        {t('activity.view')}
      </Link>
    );
  }
  if (targetType === 'ontology') {
    return (
      <Link to="/ontology" search={{ ontology: targetId }} className={className}>
        {t('activity.view')}
      </Link>
    );
  }
  if (targetType === 'document') {
    return (
      <Link to="/documents" className={className}>
        {t('activity.view')}
      </Link>
    );
  }
  if (targetType === 'release') {
    return (
      <Link to="/releases" className={className}>
        {t('activity.view')}
      </Link>
    );
  }
  return null;
}
