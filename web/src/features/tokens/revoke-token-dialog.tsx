import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { useToast } from '@/components/feedback/toast';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { useErrorMessage } from '@/i18n/error-message';

import { revokeToken, tokenListKey, type AccessToken } from './api';

export function RevokeTokenDialog({ token }: { token: AccessToken }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const mutation = useMutation({
    networkMode: 'always',
    mutationFn: () => revokeToken(token.id),
    onSuccess: async () => {
      setOpen(false);
      toast.success(t('tokens.revoke.success'));
      await queryClient.invalidateQueries({ queryKey: tokenListKey });
    },
    onError: (error) => {
      // Gone already (revoked elsewhere): the list is stale.
      if (error instanceof ApiError && error.code === 'token.not_found') {
        void queryClient.invalidateQueries({ queryKey: tokenListKey });
      }
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => {
      if (mutation.isPending) return;
      mutation.reset();
      setOpen(next);
    }}>
      <DialogTrigger disabled={mutation.isPending} className={buttonVariants({ variant: 'secondary', size: 'sm' })}>
        {t('tokens.revoke.action')}
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t('tokens.revoke.title')}</DialogTitle>
        <DialogDescription className="break-words">{t('tokens.revoke.confirm', { name: token.name })}</DialogDescription>
        {mutation.isError ? <InlineNotice tone="error" className="mt-4">{message(mutation.error)}</InlineNotice> : null}
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose disabled={mutation.isPending} className={buttonVariants({ variant: 'secondary' })}>{t('tokens.cancel')}</DialogClose>
          <Button variant="destructive" loading={mutation.isPending} onClick={() => mutation.mutate()}>{t('tokens.revoke.title')}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
