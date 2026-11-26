import { Copy } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/feedback/toast';
import { Button } from '@/components/ui/button';

async function copyText(button: HTMLButtonElement, value: string): Promise<boolean> {
  try {
    if (typeof navigator.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // A browser that denies clipboard writes may still allow copying the user's selection.
  }

  if (!button.isConnected || typeof document.execCommand !== 'function') return false;
  const previousFocus = document.activeElement;
  const field = document.createElement('textarea');
  field.className = 'sr-only';
  field.tabIndex = -1;
  field.readOnly = true;
  field.value = value;
  // Keep the selection inside the active focus trap when copying a newly created token.
  button.after(field);
  try {
    field.focus({ preventScroll: true });
    field.select();
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    field.remove();
    if (previousFocus instanceof HTMLElement) previousFocus.focus({ preventScroll: true });
  }
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [failed, setFailed] = useState(false);

  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        variant="secondary"
        size="sm"
        onClick={async (event) => {
          const copied = await copyText(event.currentTarget, value);
          setFailed(!copied);
          if (copied) toast.success(t('tokens.copy.success'));
        }}
      >
        <Copy aria-hidden />
        {label}
      </Button>
      {failed ? <p role="alert" className="text-sm text-error-strong">{t('tokens.copy.failed')}</p> : null}
    </div>
  );
}
