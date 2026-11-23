import { Link, useRouterState } from '@tanstack/react-router';
import { ChevronRight, PanelLeft, Sparkles } from 'lucide-react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';

import { navItemForPath } from '@/app/navigation';
import { AiStatusIndicator } from '@/features/ai/ai-status';
import { Button } from '@/components/ui/button';
import { Kbd } from '@/components/ui/kbd';
import { Separator } from '@/components/ui/separator';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';
import { isApplePlatform } from '@/lib/platform';

import { ASSISTANT_PANEL_ID } from './assistant-panel';
import { LanguageMenu, ThemeMenu } from './preference-menus';
import { UserMenu } from './user-menu';

interface TopbarProps {
  sidebarLabel: string;
  onToggleSidebar: () => void;
  assistantOpen: boolean;
  onToggleAssistant: () => void;
  assistantToggleRef?: Ref<HTMLButtonElement>;
}

export function Topbar({ sidebarLabel, onToggleSidebar, assistantOpen, onToggleAssistant, assistantToggleRef }: TopbarProps) {
  const { t } = useTranslation();
  const assistantLabel = t(assistantOpen ? 'shell.closeAssistant' : 'shell.openAssistant');
  const shortcut = t('shell.assistantShortcut', { key: isApplePlatform() ? '⌘' : 'Ctrl' });

  return (
    <header className="z-20 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-background px-4 lg:px-6">
      <Tooltip content={sidebarLabel} side="bottom">
        <Button variant="ghost" size="icon" aria-label={sidebarLabel} onClick={onToggleSidebar} className="-ml-2">
          <PanelLeft aria-hidden />
        </Button>
      </Tooltip>
      <Breadcrumbs />

      <div className="ml-auto flex items-center gap-1">
        <AiStatusIndicator />
        <Tooltip
          side="bottom"
          content={
            <span className="flex items-center gap-2">
              {assistantLabel}
              <Kbd>{shortcut}</Kbd>
            </span>
          }
        >
          <Button
            ref={assistantToggleRef}
            variant="ghost"
            aria-label={assistantLabel}
            aria-expanded={assistantOpen}
            aria-controls={assistantOpen ? ASSISTANT_PANEL_ID : undefined}
            aria-keyshortcuts="Control+J Meta+J"
            onClick={onToggleAssistant}
            className={cn(
              'gap-2 px-2.5 text-info-strong hover:bg-info-soft hover:text-info-strong sm:px-3',
              assistantOpen && 'bg-info-soft',
            )}
          >
            <Sparkles aria-hidden />
            <span className="hidden sm:inline">{t('assistant.title')}</span>
          </Button>
        </Tooltip>
        <LanguageMenu />
        <ThemeMenu />
        <Separator orientation="vertical" className="mx-1.5 h-6" />
        <UserMenu />
      </div>
    </header>
  );
}

function Breadcrumbs() {
  const { t } = useTranslation();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const item = navItemForPath(pathname);
  const isHome = !item || item.to === '/';

  return (
    <nav aria-label={t('shell.breadcrumb')} className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {isHome ? (
          <li className="truncate font-semibold text-foreground" aria-current="page">
            {t('nav.workbench')}
          </li>
        ) : (
          <>
            <li className="hidden sm:block">
              <Link to="/" className="rounded text-muted-foreground transition-colors hover:text-foreground">
                {t('nav.workbench')}
              </Link>
            </li>
            <li aria-hidden className="hidden text-muted-foreground sm:block">
              <ChevronRight className="size-4" />
            </li>
            <li className="truncate font-semibold text-foreground" aria-current="page">
              {t(`nav.${item.key}`)}
            </li>
          </>
        )}
      </ol>
    </nav>
  );
}
