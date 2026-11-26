import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Pagination } from '@/components/ui/pagination';
import { RelativeTime } from '@/components/ui/relative-time';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { usePagination } from '@/lib/pagination';

import type { AccessToken } from './api';
import { RevokeTokenDialog } from './revoke-token-dialog';

/** Re-evaluate the rows when a listed token expires, including while the page stays open. */
function useExpiryClock(tokens: AccessToken[]) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    let next = Infinity;
    for (const token of tokens) {
      const expires = Date.parse(token.expiresAt);
      if (token.revokedAt === null && expires > now) next = Math.min(next, expires);
    }
    if (!Number.isFinite(next)) return;
    // Browsers accept at most a signed 32-bit delay, shorter than the longest token lifetime.
    const delay = Math.min(2_147_483_647, Math.max(0, next - Date.now()));
    const timer = window.setTimeout(() => setNow(Date.now()), delay);
    return () => window.clearTimeout(timer);
  }, [tokens, now]);
  return now;
}

export function TokenTable({ tokens, showOwner }: { tokens: AccessToken[]; showOwner: boolean }) {
  const { t } = useTranslation();
  const now = useExpiryClock(tokens);
  const page = usePagination(tokens.length);
  return (
    <>
      <div className="max-h-[65dvh] overflow-auto">
        <Table aria-label={t('tokens.title')}>
          <TableHeader>
            <TableRow>
              <TableHead>{t('tokens.columns.name')}</TableHead>
              {showOwner ? <TableHead>{t('tokens.columns.owner')}</TableHead> : null}
              <TableHead>{t('tokens.columns.prefix')}</TableHead>
              <TableHead>{t('tokens.columns.scopes')}</TableHead>
              <TableHead>{t('tokens.columns.created')}</TableHead>
              <TableHead>{t('tokens.columns.expires')}</TableHead>
              <TableHead>{t('tokens.columns.lastUsed')}</TableHead>
              <TableHead><span className="sr-only">{t('tokens.columns.actions')}</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tokens.slice(page.start, page.end).map((token) => {
              const revoked = token.revokedAt !== null;
              const inactive = revoked || Date.parse(token.expiresAt) <= now;
              return (
                <TableRow key={token.id} className={inactive ? 'text-muted-foreground' : undefined}>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="break-all font-medium">{token.name}</span>
                      {inactive ? <Badge>{t(revoked ? 'tokens.revoked' : 'tokens.expired')}</Badge> : null}
                    </div>
                  </TableCell>
                  {showOwner ? <TableCell>{token.owner.displayName}</TableCell> : null}
                  <TableCell><code>{token.prefix}</code></TableCell>
                  <TableCell>
                    <ul className="space-y-1">
                      {token.scopes.map((scope) => <li key={scope}><code>{scope}</code></li>)}
                    </ul>
                  </TableCell>
                  <TableCell><RelativeTime value={token.createdAt} /></TableCell>
                  <TableCell><RelativeTime value={token.expiresAt} /></TableCell>
                  <TableCell>{token.lastUsedAt ? <RelativeTime value={token.lastUsedAt} /> : t('tokens.neverUsed')}</TableCell>
                  <TableCell>{inactive ? null : <RevokeTokenDialog token={token} />}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <Pagination state={page} total={tokens.length} />
    </>
  );
}
