import { CircleCheck, CircleX, Info, TriangleAlert, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export type NoticeTone = 'info' | 'warning' | 'error' | 'success';

const tones: Record<NoticeTone, { icon: LucideIcon; className: string; iconClassName: string }> = {
  info: { icon: Info, className: 'border-info/25 bg-info-soft', iconClassName: 'text-info-strong' },
  warning: { icon: TriangleAlert, className: 'border-warning/35 bg-warning-soft', iconClassName: 'text-warning-strong' },
  error: { icon: CircleX, className: 'border-error/30 bg-error-soft', iconClassName: 'text-error-strong' },
  success: { icon: CircleCheck, className: 'border-success/35 bg-success-soft', iconClassName: 'text-success-strong' },
};

interface InlineNoticeProps {
  tone: NoticeTone;
  /** What happened, in a few words. */
  title?: ReactNode;
  /** What it means and what to do next. */
  children?: ReactNode;
  /** Optional action, e.g. a retry button. */
  action?: ReactNode;
  /**
   * Announce the notice to screen readers as it appears (default). Off for notices that are part of
   * loaded content, such as past failures in a history list, which would otherwise all be read out.
   */
  announce?: boolean;
  className?: string;
}

/**
 * In-page banner. Warnings the user must know about are yellow, errors red (ui-guidelines §4);
 * errors are announced immediately (`role="alert"`) unless `announce` is off.
 */
export function InlineNotice({ tone, title, children, action, announce = true, className }: InlineNoticeProps) {
  const { icon: Icon, className: toneClassName, iconClassName } = tones[tone];
  return (
    <div
      role={announce ? (tone === 'error' ? 'alert' : 'status') : undefined}
      className={cn('flex items-start gap-3 rounded-lg border px-4 py-3 text-sm', toneClassName, className)}
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', iconClassName)} aria-hidden />
      <div className="min-w-0 flex-1 space-y-0.5">
        {title ? <p className={cn('font-semibold', iconClassName)}>{title}</p> : null}
        {children ? <div className="text-foreground">{children}</div> : null}
        {action ? <div className="pt-2">{action}</div> : null}
      </div>
    </div>
  );
}
