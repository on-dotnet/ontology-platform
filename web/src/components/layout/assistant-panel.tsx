import { CircleCheck, ShieldCheck, Sparkles, X } from 'lucide-react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';

export const ASSISTANT_PANEL_ID = 'assistant-panel';

interface AssistantPanelProps {
  /** Label of the page the user is on; the assistant will use it as context. */
  pageLabel: string;
  onClose: () => void;
  ref?: Ref<HTMLElement>;
}

const capabilityKeys = ['assistant.capabilityExtract', 'assistant.capabilityExplain', 'assistant.capabilityAsk'] as const;

/** Right-hand AI assistant panel. M0 shows what it will do; no fake input. */
export function AssistantPanel({ pageLabel, onClose, ref }: AssistantPanelProps) {
  const { t } = useTranslation();
  const closeLabel = t('shell.closeAssistant');

  return (
    <aside
      id={ASSISTANT_PANEL_ID}
      ref={ref}
      tabIndex={-1}
      aria-labelledby={`${ASSISTANT_PANEL_ID}-title`}
      className={cn(
        'flex w-[22.5rem] shrink-0 flex-col border-l border-border bg-card outline-none',
        // Overlays the content below 1280px, sits beside it on wide screens.
        'max-xl:fixed max-xl:bottom-0 max-xl:right-0 max-xl:top-16 max-xl:z-30 max-xl:w-[min(22.5rem,100vw)] max-xl:shadow-popover',
      )}
    >
      <div className="flex h-16 shrink-0 items-center gap-3 border-b border-border px-4">
        <span className="flex size-9 items-center justify-center rounded-lg bg-info-soft text-info-strong">
          <Sparkles className="size-4.5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={`${ASSISTANT_PANEL_ID}-title`} className="text-sm font-semibold leading-tight text-foreground">
            {t('assistant.title')}
          </h2>
          <p className="truncate text-xs text-muted-foreground">{t('assistant.context', { page: pageLabel })}</p>
        </div>
        <Tooltip content={closeLabel} side="bottom">
          <Button variant="ghost" size="icon-sm" aria-label={closeLabel} onClick={onClose}>
            <X aria-hidden />
          </Button>
        </Tooltip>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-8">
        <div className="flex flex-col items-center text-center">
          <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-info-soft text-info-strong">
            <Sparkles className="size-6" aria-hidden strokeWidth={1.75} />
          </div>
          <Badge tone="info" className="mb-3">
            {t('common.comingSoon')}
          </Badge>
          <h3 className="text-base font-semibold text-foreground">{t('assistant.emptyTitle')}</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">{t('assistant.emptyDescription')}</p>
        </div>

        <div className="mt-8 rounded-xl border border-border bg-background/60 p-4">
          <p className="text-xs font-semibold text-muted-foreground">{t('assistant.capabilitiesLabel')}</p>
          <ul className="mt-3 space-y-2.5">
            {capabilityKeys.map((key) => (
              <li key={key} className="flex gap-2.5 text-sm text-foreground">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-info-strong" aria-hidden />
                <span>{t(key)}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-4 flex gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="size-4 shrink-0" aria-hidden />
          <span>{t('assistant.reviewNote')}</span>
        </p>
      </div>
    </aside>
  );
}
