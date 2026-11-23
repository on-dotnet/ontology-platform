import { CircleAlert, FileText } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { QueryState } from '@/components/states/query-state';
import { Skeleton } from '@/components/ui/skeleton';
import type { Evidence } from '@/features/ontologies/api';
import { cn } from '@/lib/cn';

import { useChunk, useDocument } from './api';

/** Splits `text` around [start, end) when the range is valid; null when the quote has no usable position. */
export function highlightRange(
  text: string,
  start: number | null,
  end: number | null,
): { before: string; match: string; after: string } | null {
  if (start === null || end === null || start < 0 || end <= start || end > text.length) return null;
  return { before: text.slice(0, start), match: text.slice(start, end), after: text.slice(end) };
}

/**
 * The chunk an AI quote was taken from, with the quote highlighted, plus the document name and page or
 * section. Quotes without a position are flagged as "not found in the source".
 */
export function EvidenceExcerpt({ evidence, className }: { evidence: Evidence; className?: string }) {
  const { t } = useTranslation();
  const chunk = useChunk(evidence.documentId, evidence.chunkId);
  const document = useDocument(evidence.documentId);
  const markRef = useRef<HTMLElement>(null);
  const parts = chunk.data ? highlightRange(chunk.data.text, evidence.charStart, evidence.charEnd) : null;
  // No position from the pipeline, or one that does not fit the chunk text.
  const notFound = evidence.charStart === null || evidence.charEnd === null || (chunk.data !== undefined && parts === null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [chunk.data, evidence.id]);

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="inline-flex min-w-0 items-center gap-1.5 font-medium text-foreground">
          <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {document.data ? (
            <span className="truncate">{document.data.filename}</span>
          ) : document.isPending ? (
            <Skeleton className="h-4 w-32" />
          ) : (
            <span className="text-muted-foreground">{t('evidence.unknownDocument')}</span>
          )}
        </span>
        {chunk.data?.page ? <span className="text-muted-foreground">{t('evidence.page', { page: chunk.data.page })}</span> : null}
        {chunk.data?.heading ? (
          <span className="min-w-0 truncate text-muted-foreground" title={chunk.data.heading}>
            {t('evidence.section', { heading: chunk.data.heading })}
          </span>
        ) : null}
      </div>

      {notFound ? (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-sm font-medium text-warning-strong">
            <CircleAlert className="size-4 shrink-0" aria-hidden />
            {t('evidence.notFound')}
          </p>
          <blockquote className="border-l-2 border-warning pl-3 text-sm text-foreground">{evidence.quote}</blockquote>
        </div>
      ) : null}

      <QueryState
        query={chunk}
        loading={
          <div className="space-y-2" role="status" aria-busy>
            <span className="sr-only">{t('common.loading')}</span>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        }
      >
        {(data) => (
            <section
              className="max-h-[28rem] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-background p-4 text-sm leading-relaxed text-foreground"
              aria-label={t('evidence.sourceText')}
            >
              {parts ? (
                <>
                  {parts.before}
                  <mark
                    ref={markRef}
                    className="rounded bg-warning-soft px-0.5 font-medium text-foreground ring-1 ring-warning/60"
                  >
                    {parts.match}
                  </mark>
                  {parts.after}
                </>
              ) : (
                data.text
              )}
            </section>
        )}
      </QueryState>
    </div>
  );
}
