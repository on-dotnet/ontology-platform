import { Sparkles, X } from 'lucide-react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';

import type { NavItem } from '@/app/navigation';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import { AssistantWorkspace } from '@/features/assistant/assistant-workspace';
import { panelMarker } from '@/features/assistant/focus';
import { cn } from '@/lib/cn';

export const ASSISTANT_PANEL_ID = 'assistant-panel';

interface AssistantPanelProps {
  /** The section the user is on; sent to the assistant as context and named in the header. */
  page: NavItem['key'];
  onClose: () => void;
  ref?: Ref<HTMLElement>;
}

/** Right-hand AI assistant panel (spec 002 §10): context, instruction, requests and their results. */
export function AssistantPanel({ page, onClose, ref }: AssistantPanelProps) {
  const { t } = useTranslation();
  const closeLabel = t('shell.closeAssistant');

  return (
    <aside
      id={ASSISTANT_PANEL_ID}
      ref={ref}
      tabIndex={-1}
      aria-labelledby={`${ASSISTANT_PANEL_ID}-title`}
      {...panelMarker}
      className={cn(
        'flex w-[24rem] shrink-0 flex-col border-l border-border bg-card outline-none',
        // Overlays the content below Tailwind's xl (80rem: 1280px at the default font size, more when
        // the user enlarges it), sits beside it on wider screens.
        'max-xl:fixed max-xl:bottom-0 max-xl:right-0 max-xl:top-16 max-xl:z-30 max-xl:w-[min(24rem,100vw)] max-xl:shadow-popover',
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
          <p className="truncate text-xs text-muted-foreground">{t('assistant.context', { page: t(`nav.${page}`) })}</p>
        </div>
        <Tooltip content={closeLabel} side="bottom">
          <Button variant="ghost" size="icon-sm" aria-label={closeLabel} onClick={onClose}>
            <X aria-hidden />
          </Button>
        </Tooltip>
      </div>
      <AssistantWorkspace page={page} />
    </aside>
  );
}
