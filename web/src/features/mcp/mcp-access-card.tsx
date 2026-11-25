import { Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

/** Settings card: how external agents connect over MCP (spec 003, 12.5). A placeholder until
 * M3 batch 6a. */
export function McpAccessCard() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardContent className="flex items-center gap-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-info-soft text-info-strong">
          <Bot className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-foreground">{t('mcp.title')}</h2>
            <Badge tone="info">{t('common.comingSoon')}</Badge>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">{t('mcp.description')}</p>
        </div>
      </CardContent>
    </Card>
  );
}
