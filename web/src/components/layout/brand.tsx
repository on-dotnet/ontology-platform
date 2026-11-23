import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/cn';

/** Product mark: a small concept graph on a primary-colored tile. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('size-8 shrink-0', className)} aria-hidden focusable="false">
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g className="stroke-primary-foreground" strokeWidth="2" strokeLinecap="round" fill="none">
        <path d="M10 11.5 16 8l6 3.5M10 11.5v8L16 23l6-3.5v-8M16 15.5V23M10 11.5l6 4 6-4" />
      </g>
      <g className="fill-primary-foreground">
        <circle cx="16" cy="8" r="2.2" />
        <circle cx="10" cy="11.5" r="2.2" />
        <circle cx="22" cy="11.5" r="2.2" />
        <circle cx="16" cy="23" r="2.2" />
      </g>
    </svg>
  );
}

export function BrandName({ className }: { className?: string }) {
  const { t } = useTranslation();
  return <span className={cn('truncate text-base font-semibold tracking-tight text-foreground', className)}>{t('app.name')}</span>;
}
