import { Link } from '@tanstack/react-router';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@/components/feedback/inline-notice';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { QuestionError } from './question-error';

interface Props {
  text: string;
  setText: (text: string) => void;
  onSubmit: (text: string) => void;
  sending: boolean;
  unconfigured: boolean;
  error: Error | null;
}

export function QuestionForm({ text, setText, onSubmit, sending, unconfigured, error }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const disabled = sending || unconfigured || !text.trim();
  return (
    <Card className="p-5">
      <form aria-label={t('qa.question')} className="space-y-3" onSubmit={(event) => {
        event.preventDefault();
        if (!disabled) onSubmit(text.trim());
      }}>
        <Label htmlFor={id}>{t('qa.question')}</Label>
        <Textarea id={id} value={text} required disabled={unconfigured} aria-describedby={`${id}-limit ${id}-notice`}
          onChange={(event) => setText(Array.from(event.target.value).slice(0, 500).join(''))} />
        <p id={`${id}-limit`} className="text-xs text-muted-foreground">{t('qa.questionLimit')}</p>
        <p id={`${id}-notice`} className="text-xs text-muted-foreground">{t('qa.dataNotice')}</p>
        {unconfigured ? (
          <InlineNotice tone="warning" title={t('qa.errors.ai.not_configured')} action={
            <Link to="/settings" className={buttonVariants({ variant: 'secondary', size: 'sm' })}>{t('qa.settings')}</Link>
          } />
        ) : error && <QuestionError error={error} />}
        <Button type="submit" loading={sending} disabled={disabled}>{t('qa.ask')}</Button>
      </form>
    </Card>
  );
}
