import { Toast } from '@base-ui/react/toast';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/api/errors';
import { useToast } from '@/components/feedback/toast';
import { usePermissions } from '@/features/auth/permissions';
import { elementName, ontologyKeys, saveEdits, useAppliesEdits, type EditItem, type EditResult, type Element } from '@/features/ontologies/api';
import { changeSetKeys } from '@/features/review/api';
import { useErrorMessage } from '@/i18n/error-message';

/** 409 `element.stale`: the element changed after it was read. */
export function isStale(error: unknown): boolean {
  return isApiError(error) && error.code === 'element.stale';
}

/** Whether saving takes effect at once (true) or goes to review; decides the button labels. */
export function useAppliesOwnEdits(): boolean {
  const { canReview } = usePermissions();
  return useAppliesEdits(canReview);
}

/** Invalidates what a manual change set changes: the ontology, its change sets and the workbench counts. */
export function useRefreshAfterEdit(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ontologyKeys.all }),
      queryClient.invalidateQueries({ queryKey: changeSetKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['workbench'] }),
    ]);
  };
}

/**
 * Success toast for a save: `appliedTitle` when it took effect; otherwise that it went to review,
 * with a link to the change set.
 */
function useEditToast(): (result: EditResult, appliedTitle: string) => void {
  const { t } = useTranslation();
  // The shared `useToast` only takes text; a link to the change set needs a node as description.
  const manager = Toast.useToastManager();
  const router = useRouter();
  return (result, appliedTitle) => {
    if (result.merged) {
      manager.add({ title: appliedTitle, type: 'success' });
      return;
    }
    const target = { to: '/review/$changeSetId', params: { changeSetId: result.changeSetId } } as const;
    // Toasts render outside the router, so the link navigates through the router it was made with.
    const href = router.buildLocation(target).href;
    manager.add({
      title: t('ontologyPage.edit.submitted'),
      type: 'success',
      description: (
        <a
          href={href}
          className="rounded font-medium text-primary-strong hover:underline"
          onClick={(event) => {
            event.preventDefault();
            void router.navigate(target);
          }}
        >
          {t('ontologyPage.edit.goReview')}
        </a>
      ),
    });
  };
}

export interface SaveVariables {
  items: EditItem[];
  /** Toast title when the change took effect, e.g. "Saved". */
  appliedTitle: string;
}

/**
 * Saves manual edits as a change set: merged at once for reviewers in single review mode,
 * submitted for review otherwise. Refreshes the ontology and confirms with a toast.
 */
export function useSaveEdits(ontologyId: string) {
  const apply = useAppliesOwnEdits();
  const refresh = useRefreshAfterEdit();
  const notify = useEditToast();
  const mutation = useMutation({
    mutationFn: ({ items }: SaveVariables) => saveEdits(ontologyId, { items, apply }),
    onSuccess: async (result, { appliedTitle }) => {
      await refresh();
      notify(result, appliedTitle);
    },
  });
  return { apply, mutation };
}

/** Restores a deleted element; failures (a stale revision among them) end in an error toast and a refresh. */
export function useRestoreElement(ontologyId: string) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const message = useErrorMessage();
  const refresh = useRefreshAfterEdit();
  const { mutation } = useSaveEdits(ontologyId);
  const restore = (element: Element) =>
    mutation.mutate(
      {
        items: [{ op: 'restore', kind: element.kind, targetElementId: element.id, targetRevision: element.revision }],
        appliedTitle: t('ontologyPage.edit.restored', { name: elementName(element, i18n.resolvedLanguage ?? i18n.language) || '—' }),
      },
      {
        onError: (error) => {
          toast.error(t('ontologyPage.edit.restoreFailed'), message(error));
          if (isStale(error)) void refresh();
        },
      },
    );
  /** The element being restored right now, if any. */
  const pendingId = mutation.isPending ? mutation.variables.items[0]?.targetElementId : undefined;
  return { restore, pendingId };
}
