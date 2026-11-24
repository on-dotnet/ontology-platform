import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, buttonVariants } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';

interface DiscardChangesDialogProps {
  open: boolean;
  /** What is lost; a sentence. */
  description: string;
  onKeep: () => void;
  onDiscard: () => void;
}

/** "Discard unsaved changes?" Rendered inside another dialog's content, it stacks on top of it. */
export function DiscardChangesDialog({ open, description, onKeep, onDiscard }: DiscardChangesDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onKeep();
      }}
    >
      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('ontologyPage.discard.title')}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose className={buttonVariants({ variant: 'secondary' })}>{t('ontologyPage.discard.keep')}</DialogClose>
          <Button variant="destructive" onClick={onDiscard}>
            {t('ontologyPage.discard.confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Closing a form dialog that holds unsaved changes asks first, whether by Esc, the backdrop, the
 * close button or "Cancel". The form reports whether it has changes with `setDirty`.
 */
export function useDiscardGuard(onClose: () => void) {
  const [dirty, setDirty] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const close = () => {
    setDirty(false);
    setConfirming(false);
    onClose();
  };
  return {
    setDirty,
    confirming,
    /** Closes now, e.g. after saving. */
    close,
    /** Closes, or asks first when there are unsaved changes. */
    requestClose: () => (dirty ? setConfirming(true) : close()),
    keep: () => setConfirming(false),
  };
}
