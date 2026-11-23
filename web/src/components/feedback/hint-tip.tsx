import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';
import { CircleAlert, Info } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { TooltipContent } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';

interface HintTipProps {
  /** One or two sentences (ui-guidelines §4); longer content belongs behind a "learn more" link. */
  children: ReactNode;
  /** Accessible name of the icon button; defaults to a generic "more information". */
  label?: string;
  side?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

type Tone = 'info' | 'warning';

function HintTip({ tone, children, label, side = 'top', className }: HintTipProps & { tone: Tone }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const descriptionId = useId();
  const Icon = tone === 'info' ? Info : CircleAlert;

  return (
    <BaseTooltip.Root open={open} onOpenChange={setOpen}>
      <BaseTooltip.Trigger
        type="button"
        delay={150}
        closeOnClick={false}
        aria-label={label ?? t(tone === 'info' ? 'common.moreInfo' : 'common.attention')}
        aria-describedby={descriptionId}
        // Keyboard focus and taps always open the bubble, independent of hover heuristics.
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
        className={cn(
          'inline-flex size-6 shrink-0 cursor-help items-center justify-center rounded-full align-middle transition-colors',
          'outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring',
          tone === 'info'
            ? 'text-muted-foreground hover:bg-muted hover:text-primary-strong data-[popup-open]:text-primary-strong'
            : 'text-warning-strong hover:bg-warning-soft',
          className,
        )}
      >
        <Icon className="size-4" aria-hidden />
      </BaseTooltip.Trigger>
      {/* Always in the DOM so screen readers announce the text with the button. */}
      <span id={descriptionId} className="sr-only">
        {children}
      </span>
      <TooltipContent side={side}>{children}</TooltipContent>
    </BaseTooltip.Root>
  );
}

/** ⓘ — explains a concept, field or consequence; optional to read (ui-guidelines §4). */
export function InfoTip(props: HintTipProps) {
  return <HintTip tone="info" {...props} />;
}

/** ! (warning color) — something unexpected that does not change the outcome (ui-guidelines §4). */
export function WarnTip(props: HintTipProps) {
  return <HintTip tone="warning" {...props} />;
}
