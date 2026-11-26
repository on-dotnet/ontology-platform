import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { InlineNotice } from '@/components/feedback/inline-notice';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { useErrorMessage } from '@/i18n/error-message';

import { SuggestionForm } from './suggestion-form';
import { SuggestionResult } from './suggestion-result';

type Request = { ontologyId: string; body: components['schemas']['BindingSuggestionCreate'] };

interface Props {
  dataSourceId?: string;
  typeIds?: string[];
  ontologyId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SuggestBindingsDialog({ open, onOpenChange, ...context }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && (
        <DialogContent closeLabel={t('common.close')} className="max-h-[85dvh] space-y-4 overflow-y-auto">
          <DialogTitle className="pr-8">{t('bindings.suggest.title')}</DialogTitle>
          <SuggestionSession {...context} onClose={() => onOpenChange(false)} />
        </DialogContent>
      )}
    </Dialog>
  );
}

function SuggestionSession({ dataSourceId, typeIds, ontologyId, onClose }: Omit<Props, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const message = useErrorMessage();
  const [accepted, setAccepted] = useState<components['schemas']['BindingSuggestion'] | null>(null);
  const create = useMutation({
    mutationFn: ({ ontologyId: id, body }: Request) =>
      unwrap(api.POST('/api/ontologies/{id}/binding-suggestions', { params: { path: { id } }, body })),
    onSuccess: (request) => setAccepted(request),
  });

  return (
    <>
      {create.isError && <InlineNotice tone="error">{message(create.error)}</InlineNotice>}
      {accepted ? (
        <SuggestionResult key={accepted.id} initial={accepted} retryPending={create.isPending} onClose={onClose}
          onRetry={() => { if (create.variables) create.mutate(create.variables); }} />
      ) : (
        <SuggestionForm dataSourceId={dataSourceId} ontologyId={ontologyId} disabled={create.isPending}
          onSubmit={(id, body) => create.mutate({ ontologyId: id, body: typeIds ? { ...body, typeIds } : body })} />
      )}
    </>
  );
}
