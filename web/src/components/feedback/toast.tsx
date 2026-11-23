import { Toast } from '@base-ui/react/toast';
import { CircleCheck, CircleX, Info, X } from 'lucide-react';
import { useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/cn';

type ToastType = 'success' | 'error' | 'info';

const icons = {
  success: { icon: CircleCheck, className: 'text-success-strong' },
  error: { icon: CircleX, className: 'text-error-strong' },
  info: { icon: Info, className: 'text-info-strong' },
} as const;

function isToastType(value: unknown): value is ToastType {
  return value === 'success' || value === 'error' || value === 'info';
}

/** Bottom-right toasts. Success toasts close after 3 seconds (ui-guidelines §4). */
export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider timeout={3000} limit={3}>
      {children}
      <ToastViewport />
    </Toast.Provider>
  );
}

function ToastViewport() {
  const { toasts } = Toast.useToastManager();
  const { t } = useTranslation();
  return (
    <Toast.Portal>
      <Toast.Viewport className="fixed bottom-4 right-4 z-70 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2 outline-none">
        {toasts.map((toast) => {
          const { icon: Icon, className } = icons[isToastType(toast.type) ? toast.type : 'info'];
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
      success: (title: string, description?: string) => manager.add({ title, description, type: 'success' }),
      error: (title: string, description?: string) =>
        manager.add({ title, description, type: 'error', priority: 'high', timeout: 8000 }),
    }),
    [manager],
  );
}
