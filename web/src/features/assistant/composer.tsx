import { Send } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useErrorMessage } from '@/i18n/error-message';
import { cn } from '@/lib/cn';
import { isImeComposing } from '@/lib/keyboard';

import { MESSAGE_MAX_LENGTH, messageLength } from './api';
import { autofocusMarker, PANEL_SELECTOR } from './focus';

/** The counter appears near the limit, so it does not distract while typing short requests. */
const COUNTER_FROM = Math.floor(MESSAGE_MAX_LENGTH * 0.9);

interface ComposerProps {
  /** Resolves once the request was accepted; the field is cleared then. */
  onSend: (message: string) => Promise<unknown>;
  sending: boolean;
  /** The last send failure, if any. */
  sendError: unknown;
}

/** Multi-line instruction for the assistant: Enter sends, Shift + Enter starts a new line. */
export function Composer({ onSend, sending, sendError }: ComposerProps) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const fieldId = useId();
  const hintId = useId();
  const errorId = useId();
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState(false);

  // When the panel opened before the composer could render, focus still sits on the panel itself.
  useEffect(() => {
    const field = fieldRef.current;
    if (field && document.activeElement === field.closest(PANEL_SELECTOR)) field.focus();
  }, []);

  const length = messageLength(text);
  const tooLong = length > MESSAGE_MAX_LENGTH;
  const error = tooLong
    ? t('assistant.composer.tooLong', { max: MESSAGE_MAX_LENGTH })
    : submitted && length === 0
      ? t('assistant.composer.required')
      : undefined;

  const send = () => {
    setSubmitted(true);
    if (length === 0 || tooLong) {
      fieldRef.current?.focus();
      return;
    }
    onSend(text.trim()).then(
      () => {
        setText('');
        setSubmitted(false);
      },
      // The failure is shown from `sendError`; the text stays for another try.
      () => undefined,
    );
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    send();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Only a plain Enter sends; while an input method composes, Enter picks a candidate.
    if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    if (isImeComposing(event.nativeEvent)) return;
    event.preventDefault();
    if (!sending) send();
  };

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-2">
      {sendError ? (
        <InlineNotice tone="error" title={t('assistant.composer.failedTitle')}>
          {message(sendError)}
        </InlineNotice>
      ) : null}
      <label htmlFor={fieldId} className="sr-only">
        {t('assistant.composer.label')}
      </label>
      <Textarea
        ref={fieldRef}
        id={fieldId}
        value={text}
        rows={3}
        placeholder={t('assistant.composer.placeholder')}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${errorId} ${hintId}` : hintId}
        className="min-h-20 resize-none"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        {...autofocusMarker}
      />
      {error ? (
        <p id={errorId} className="text-sm text-error-strong">
          {error}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <p id={hintId} className="min-w-0 flex-1 text-xs text-muted-foreground">
          {t('assistant.composer.hint')}
          {length >= COUNTER_FROM ? (
            <span className={cn('ml-2 tabular-nums', tooLong && 'font-semibold text-error-strong')}>
              {t('assistant.composer.count', { length, max: MESSAGE_MAX_LENGTH })}
            </span>
          ) : null}
        </p>
        <Button type="submit" size="sm" loading={sending}>
          {sending ? null : <Send aria-hidden />}
          {t('assistant.composer.send')}
        </Button>
      </div>
    </form>
  );
}
