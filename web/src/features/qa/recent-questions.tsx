import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import type { Question } from './api';

const statuses: Record<Question['status'], [string, BadgeTone]> = {
  queued: ['qa.queued', 'neutral'],
  running: ['assistant.progress.running', 'info'],
  answered: ['qa.answered', 'success'],
  unanswerable: ['cq.result.unanswerable', 'warning'],
  failed: ['datasources.status.failed', 'error'],
};

interface Props {
  items: Question[];
  selected?: Question;
  selectedId?: string;
  onSelect: (id: string) => void;
  onExample: (text: string) => void;
  disabled: boolean;
  state?: ReactNode;
}

export function RecentQuestions({ items, selected, selectedId, onSelect, onExample, disabled, state }: Props) {
  const { t } = useTranslation();
  return (
    <Card className="min-w-0">
      <CardHeader><CardTitle>{t('qa.recent')}</CardTitle></CardHeader>
      <CardContent>
        {state ?? (items.length ? (
          <ul aria-label={t('qa.recent')} className="space-y-1">
            {items.map((item) => {
              const [key, tone] = statuses[selected?.id === item.id ? selected.status : item.status];
              return <li key={item.id}>
                <Button variant={item.id === selectedId ? 'soft' : 'ghost'} className="h-auto w-full justify-between py-2"
                  aria-pressed={item.id === selectedId} onClick={() => onSelect(item.id)}>
                  <span className="truncate" title={item.question}>{item.question}</span>
                  <Badge tone={tone}>{t(key)}</Badge>
                </Button>
              </li>;
            })}
          </ul>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{t('qa.tryAsking')}</p>
            <Button variant="secondary" className="h-auto whitespace-normal py-2 text-left"
              disabled={disabled} onClick={() => onExample(t('qa.example'))}>{t('qa.example')}</Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
