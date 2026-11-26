import { Bot } from 'lucide-react';
import { Trans, useTranslation } from 'react-i18next';

import { Card, CardContent } from '@/components/ui/card';
import { CopyButton } from '@/features/tokens/copy-button';

const PROTOCOL_VERSION = '2026-07-28';

/** Settings card: how external agents connect over MCP (spec 003, 12.5). The endpoint is
 * served by the same origin as the platform, behind the same proxy. */
export function McpAccessCard() {
  const { t } = useTranslation();
  const endpoint = `${window.location.origin}/mcp`;
  const config = JSON.stringify(
    {
      mcpServers: {
        'ontology-platform': {
          type: 'http',
          url: endpoint,
          headers: { Authorization: `Bearer ${t('mcp.tokenPlaceholder')}` },
        },
      },
    },
    null,
    2,
  );

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-center gap-4">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-info-soft text-info-strong">
            <Bot className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-foreground">{t('mcp.title')}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{t('mcp.description')}</p>
          </div>
        </div>

        <section className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium text-foreground">{t('mcp.endpoint')}</h3>
          <div className="flex flex-wrap items-start gap-2">
            <code className="min-w-0 break-all rounded-md bg-muted px-2 py-1.5 font-mono text-xs text-foreground">
              {endpoint}
            </code>
            <CopyButton value={endpoint} label={t('mcp.copyEndpoint')} />
          </div>
        </section>

        <section className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium text-foreground">{t('mcp.config')}</h3>
          <pre
            data-testid="mcp-client-config"
            className="max-w-full overflow-x-auto rounded-md bg-muted px-2 py-1.5 font-mono text-xs text-foreground"
          >
            {config}
          </pre>
          <CopyButton value={config} label={t('mcp.copyConfig')} />
        </section>

        <p className="text-sm text-muted-foreground">
          <Trans
            i18nKey="mcp.hint"
            values={{ version: PROTOCOL_VERSION, ontologyScope: 'ontology:read', objectsScope: 'objects:read' }}
            components={{ code: <code className="font-mono text-xs text-foreground" /> }}
          />
        </p>
      </CardContent>
    </Card>
  );
}
