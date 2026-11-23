import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { ChevronDown, LogOut, UserRoundCog } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { Avatar } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { clearSession, logout, useCurrentUser } from '@/features/auth/api';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';

export function UserMenu() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const message = useErrorMessage();

  const signOut = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      clearSession(queryClient);
      await navigate({ to: '/login', replace: true });
    },
    onError: (error) => toast.error(t('user.signOutFailed'), message(error)),
  });

  if (!user) return null;
  const name = user.displayName || user.username;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        // Includes the visible name so voice control ("click 王工") matches (WCAG 2.5.3).
        aria-label={t('user.menu', { name })}
        className={cn(
          'flex h-10 items-center gap-2 rounded-lg pl-1 pr-2 text-sm transition-colors hover:bg-muted',
          'outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
          'data-[popup-open]:bg-muted',
        )}
      >
        <Avatar name={name} className="size-8" />
        <span className="hidden max-w-32 truncate font-medium text-foreground md:inline">{name}</span>
        <ChevronDown className="hidden size-4 text-muted-foreground md:inline" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <div className="flex items-center gap-3 px-2.5 py-2">
          <Avatar name={name} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-foreground">{name}</p>
            <p className="truncate text-xs text-muted-foreground">{user.username}</p>
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void navigate({ to: '/settings' })}>
          <UserRoundCog aria-hidden />
          {t('user.settings')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={signOut.isPending}
          onClick={() => signOut.mutate()}
          className="text-error-strong [&_svg]:text-error-strong"
        >
          <LogOut aria-hidden />
          {t('user.signOut')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
