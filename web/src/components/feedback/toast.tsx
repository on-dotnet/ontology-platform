import { Toast } from '@base-ui/react/toast';
import { CircleCheck, CircleX, Info, X } from 'lucide-react';
import { useMemo, type MouseEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/cn';

type ToastType = 'success' | 'error' | 'info';

/** A follow-up offered in a toast, such as "Undo" or "Go to review"; the toast closes once it is used. */
export interface ToastAction {
  /** Verb first, like every button (ui-guidelines §6). */
  label: string;
  onClick: () => void;
  /**
   * Address of the page the action opens. Renders a link, so it can also be opened in a new tab;
   * a plain click runs `onClick` instead (toasts sit outside the router, so the caller navigates).
   */
  href?: string;
}

const icons = {
  success: { icon: CircleCheck, className: 'text-success-strong' },
  error: { icon: CircleX, className: 'text-error-strong' },
  info: { icon: Info, className: 'text-info-strong' },
} as const;

function isToastType(value: unknown): value is ToastType {
  return value === 'success' || value === 'error' || value === 'info';
}

/** The action stored with a toast; toast data is untyped, so it is checked before use. */
function toastAction(data: unknown): ToastAction | undefined {
  if (typeof data !== 'object' || data === null || !('action' in data)) return undefined;
  const { action } = data;
  if (typeof action !== 'object' || action === null || !('label' in action) || !('onClick' in action)) return undefined;
  const { label, onClick } = action;
  if (typeof label !== 'string' || typeof onClick !== 'function') return undefined;
  const href = 'href' in action && typeof action.href === 'string' ? action.href : undefined;
  return { label, onClick: () => void (onClick as () => unknown)(), ...(href ? { href } : {}) };
}

/** How long a toast with an action stays: long enough to reach the action, also by keyboard. */
const ACTION_TIMEOUT = 8000;

/** Bottom-right toasts. Success toasts close after 3 seconds (ui-guidelines §4), those with an action after 8. */
export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider timeout={3000} limit={3}>
      {children}
      <ToastViewport />
    </Toast.Provider>
  );
}

const actionClassName = 'rounded text-sm font-medium text-primary-strong hover:underline';

function ToastViewport() {
  const { toasts, close } = Toast.useToastManager();
  const { t } = useTranslation();
  return (
    <Toast.Portal>
      <Toast.Viewport className="fixed bottom-4 right-4 z-70 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2 outline-none">
        {toasts.map((toast) => {
          const { icon: Icon, className } = icons[isToastType(toast.type) ? toast.type : 'info'];
          const action = toastAction(toast.data);
          const run = () => {
            action?.onClick();
            close(toast.id);
          };
          const followLink = (event: MouseEvent<HTMLAnchorElement>) => {
            // Modified clicks open the address in a new tab or window, as links do.
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            run();
          };
          return (
            <Toast.Root
              key={toast.id}
              toast={toast}
              className={cn(
                'flex items-start gap-3 rounded-xl border border-border bg-card p-4 text-sm text-foreground shadow-popover',
                'transition-[opacity,translate] duration-200',
                'data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0 data-[ending-style]:opacity-0',
              )}
            >
              <Icon className={cn('mt-0.5 size-4 shrink-0', className)} aria-hidden />
              <div className="min-w-0 flex-1">
                <Toast.Title className="font-semibold" />
                <Toast.Description className="text-muted-foreground" />
                {action ? (
                  <div className="mt-1">
                    {action.href ? (
                      <a href={action.href} className={actionClassName} onClick={followLink}>
                        {action.label}
                      </a>
                    ) : (
                      <button type="button" className={actionClassName} onClick={run}>
                        {action.label}
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
              <Toast.Close
                aria-label={t('common.close')}
                className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }), '-m-1.5 size-7')}
              >
                <X aria-hidden />
              </Toast.Close>
            </Toast.Root>
          );
        })}
      </Toast.Viewport>
    </Toast.Portal>
  );
}

export function useToast() {
  const manager = Toast.useToastManager();
  return useMemo(
    () => ({
      success: (title: string, description?: string, action?: ToastAction) =>
        manager.add({ title, description, type: 'success', ...(action ? { data: { action }, timeout: ACTION_TIMEOUT } : {}) }),
      error: (title: string, description?: string, action?: ToastAction) =>
        manager.add({ title, description, type: 'error', priority: 'high', timeout: 8000, ...(action ? { data: { action } } : {}) }),
    }),
    [manager],
  );
}
