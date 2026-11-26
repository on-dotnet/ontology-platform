import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { meQueryKey } from '@/features/auth/api';
import { usePermissions } from '@/features/auth/permissions';
import { useErrorMessage } from '@/i18n/error-message';

import { createToken, tokenListKey, type TokenInput, type TokenScope } from './api';
import { CopyButton } from './copy-button';

const scopeChoices = [
  { scope: 'ontology:read', description: 'tokens.scope.ontologyRead' },
  { scope: 'objects:read', description: 'tokens.scope.objectsRead' },
  { scope: 'changes:propose', description: 'tokens.scope.changesPropose' },
] as const satisfies readonly { scope: TokenScope; description: string }[];

export function CreateTokenDialog() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const resultTitle = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (secret !== null) resultTitle.current?.focus();
  }, [secret]);
  const mutation = useMutation({
    networkMode: 'always',
    // Keep the one-time secret out of the mutation cache as well as the list cache.
    mutationFn: async (body: TokenInput) => {
      const result = await createToken(body);
      setSecret(result.token);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tokenListKey });
    },
    onError: (error) => {
      if (isApiError(error) && error.code === 'token.scope_not_allowed') {
        void queryClient.invalidateQueries({ queryKey: meQueryKey });
      }
    },
  });

  const changeOpen = (next: boolean) => {
    if (!next && mutation.isPending) return;
    if (!next) {
      setSecret(null);
      mutation.reset();
    }
    setOpen(next);
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger className={buttonVariants()}>
        <Plus aria-hidden />
        {t('tokens.create.open')}
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        {open && (secret !== null ? (
          <>
            <DialogTitle tabIndex={-1} ref={resultTitle}>{t('tokens.create.saveTitle')}</DialogTitle>
            <InlineNotice tone="warning" className="mt-4">{t('tokens.create.saveWarning')}</InlineNotice>
            <code className="my-4 block select-all break-all rounded-lg bg-muted p-3 font-mono text-sm">{secret}</code>
            <div className="flex flex-wrap justify-end gap-2">
              <CopyButton value={secret} label={t('tokens.create.copy')} />
              <DialogClose className={buttonVariants()}>{t('tokens.create.done')}</DialogClose>
            </div>
          </>
        ) : (
          <>
            <DialogTitle>{t('tokens.create.open')}</DialogTitle>
            <TokenForm onSubmit={mutation.mutate} pending={mutation.isPending} error={mutation.error} />
          </>
        ))}
      </DialogContent>
    </Dialog>
  );
}

function TokenForm({ onSubmit, pending, error }: {
  onSubmit: (body: TokenInput) => void;
  pending: boolean;
  error: Error | null;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { canProposeViaMcp } = usePermissions();
  const id = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const scopesRef = useRef<HTMLFieldSetElement>(null);
  const [name, setName] = useState('');
  const [selectedScopes, setScopes] = useState<TokenScope[]>([]);
  const [days, setDays] = useState(90);
  const [nameTouched, setNameTouched] = useState(false);
  const [scopesTouched, setScopesTouched] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const choices = scopeChoices.filter(({ scope }) => scope !== 'changes:propose' || canProposeViaMcp);
  const scopes = selectedScopes.filter((scope) => choices.some((choice) => choice.scope === scope));
  const nameInvalid = !name.trim() || name.trim().length > 100;
  const showNameError = nameInvalid && (nameTouched || submitted);
  const showScopesError = !scopes.length && (scopesTouched || submitted);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setSubmitted(true);
    if (nameInvalid) nameRef.current?.focus();
    else if (!scopes.length) scopesRef.current?.querySelector('input')?.focus();
    else onSubmit({ name: name.trim(), scopes, expiresInDays: days });
  }

  return (
    <form noValidate onSubmit={submit} className="mt-5 space-y-4">
      {submitted && (nameInvalid || !scopes.length) ? <InlineNotice tone="error">{t('tokens.create.validation')}</InlineNotice> : null}
      {error ? <InlineNotice tone="error">{message(error)}</InlineNotice> : null}
      <div className="space-y-2">
        <Label htmlFor={id + '-name'} required>{t('tokens.columns.name')}</Label>
        <Input
          ref={nameRef}
          id={id + '-name'}
          value={name}
          maxLength={100}
          required
          disabled={pending}
          aria-invalid={showNameError || undefined}
          aria-describedby={showNameError ? id + '-name-error' : undefined}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => setNameTouched(true)}
        />
        {showNameError ? <p id={id + '-name-error'} className="text-sm text-error-strong">{t('tokens.create.nameRequired')}</p> : null}
      </div>
      <fieldset
        ref={scopesRef}
        disabled={pending}
        className="space-y-2"
        aria-describedby={showScopesError ? id + '-scope-error' : undefined}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setScopesTouched(true);
        }}
      >
        <legend className="mb-2 text-sm font-medium">
          {t('tokens.columns.scopes')} <span className="text-error-strong" aria-hidden>*</span>
        </legend>
        {choices.map(({ scope, description }) => (
          <div key={scope} className="grid grid-cols-[auto_1fr] items-center gap-x-2">
            <input
              id={id + scope}
              type="checkbox"
              value={scope}
              checked={scopes.includes(scope)}
              aria-describedby={showScopesError ? `${id}${scope}-description ${id}-scope-error` : id + scope + '-description'}
              aria-invalid={showScopesError || undefined}
              className="size-4 accent-primary focus-visible:outline-ring"
              onChange={(event) => setScopes(event.target.checked ? [...scopes, scope] : scopes.filter((item) => item !== scope))}
            />
            <Label htmlFor={id + scope} className="font-mono">{scope}</Label>
            <p id={id + scope + '-description'} className="col-start-2 text-sm text-muted-foreground">{t(description)}</p>
          </div>
        ))}
        {showScopesError ? <p id={id + '-scope-error'} className="text-sm text-error-strong">{t('tokens.create.scopeRequired')}</p> : null}
      </fieldset>
      <div className="space-y-2">
        <Label htmlFor={id + '-expiry'}>{t('tokens.create.lifetime')}</Label>
        <NativeSelect id={id + '-expiry'} value={days} disabled={pending} onChange={(event) => setDays(Number(event.target.value))}>
          {[30, 90, 365].map((count) => <option key={count} value={count}>{t('tokens.create.days', { count })}</option>)}
        </NativeSelect>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <DialogClose disabled={pending} className={buttonVariants({ variant: 'secondary' })}>{t('tokens.cancel')}</DialogClose>
        <Button type="submit" loading={pending}>{t('tokens.create.submit')}</Button>
      </div>
    </form>
  );
}
