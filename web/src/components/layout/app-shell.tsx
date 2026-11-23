import { Outlet, useRouterState } from '@tanstack/react-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { navItemForPath } from '@/app/navigation';
import { Dialog, DialogTitle, SheetContent } from '@/components/ui/dialog';
import { cn } from '@/lib/cn';
import { storage } from '@/lib/storage';
import { DESKTOP_QUERY, useMediaQuery } from '@/lib/use-media-query';

import { AssistantPanel } from './assistant-panel';
import { SidebarContent } from './sidebar';
import { Topbar } from './topbar';

const SIDEBAR_STORAGE_KEY = 'op.sidebar.collapsed';
const MAIN_ID = 'main-content';

export function AppShell() {
  const { t } = useTranslation();
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const pageLabel = t(`nav.${navItemForPath(pathname)?.key ?? 'workbench'}`);

  const [collapsed, setCollapsed] = useState(() => storage.get(SIDEBAR_STORAGE_KEY) === 'true');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const assistantRef = useRef<HTMLElement>(null);
  const assistantToggleRef = useRef<HTMLButtonElement>(null);

  const toggleSidebar = () => {
    if (!isDesktop) {
      setDrawerOpen(true);
      return;
    }
    const next = !collapsed;
    setCollapsed(next);
    storage.set(SIDEBAR_STORAGE_KEY, String(next));
  };

  const closeAssistant = useCallback(() => {
    const hadFocus = assistantRef.current?.contains(document.activeElement) ?? false;
    setAssistantOpen(false);
    if (hadFocus) assistantToggleRef.current?.focus();
  }, []);

  const toggleAssistant = useCallback(() => {
    if (assistantRef.current) closeAssistant();
    else setAssistantOpen(true);
  }, [closeAssistant]);

  // Move focus into the panel when it opens so keyboard and screen reader users land there.
  useEffect(() => {
    if (assistantOpen) assistantRef.current?.focus();
  }, [assistantOpen]);

  // Ctrl/⌘ + J toggles the assistant anywhere; Escape closes it while focus is inside.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'j') {
        event.preventDefault();
        toggleAssistant();
      } else if (event.key === 'Escape' && assistantRef.current?.contains(document.activeElement)) {
        closeAssistant();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toggleAssistant, closeAssistant]);

  const sidebarLabel = isDesktop
    ? t(collapsed ? 'shell.expandSidebar' : 'shell.collapseSidebar')
    : t('shell.openNavigation');

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <a
        href={`#${MAIN_ID}`}
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-80 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:font-medium focus:shadow-popover"
      >
        {t('app.skipToContent')}
      </a>

      <aside
        className={cn(
          'hidden shrink-0 border-r border-border bg-card transition-[width] duration-200 lg:block',
          collapsed ? 'w-[72px]' : 'w-64',
        )}
      >
        <SidebarContent collapsed={collapsed} />
      </aside>

      <Dialog open={drawerOpen && !isDesktop} onOpenChange={setDrawerOpen}>
        <SheetContent side="left" closeLabel={t('shell.closeNavigation')}>
          <DialogTitle className="sr-only">{t('nav.label')}</DialogTitle>
          <SidebarContent onNavigate={() => setDrawerOpen(false)} />
        </SheetContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          sidebarLabel={sidebarLabel}
          onToggleSidebar={toggleSidebar}
          assistantOpen={assistantOpen}
          onToggleAssistant={toggleAssistant}
          assistantToggleRef={assistantToggleRef}
        />
        <div className="flex min-h-0 flex-1">
          <main id={MAIN_ID} tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto outline-none">
            <div className="mx-auto w-full max-w-[1440px] p-4 sm:p-6">
              <Outlet />
            </div>
          </main>
          {assistantOpen ? <AssistantPanel ref={assistantRef} pageLabel={pageLabel} onClose={closeAssistant} /> : null}
        </div>
      </div>
    </div>
  );
}
