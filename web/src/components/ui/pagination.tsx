import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import { PAGE_SIZE, type PageState } from '@/lib/pagination';

interface PaginationProps {
  state: PageState;
  total: number;
  className?: string;
  /** Called after the page changed, e.g. to bring the top of the list back into view. */
  onChange?: () => void;
}

/** Previous/next controls with the range shown; nothing for a list that fits on one page. */
export function Pagination({ state, total, className, onChange }: PaginationProps) {
  const { t } = useTranslation();
  if (total <= PAGE_SIZE) return null;
  const go = (page: number) => {
    state.setPage(page);
    onChange?.();
  };
  return (
    <nav aria-label={t('pagination.label')} className={cn('flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm', className)}>
      <p aria-live="polite" className="whitespace-nowrap tabular-nums text-muted-foreground">{t('pagination.range', { from: state.start + 1, to: state.end, total })}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="whitespace-nowrap tabular-nums text-muted-foreground">{t('pagination.page', { page: state.page, pages: state.pages })}</span>
        <Button variant="secondary" size="sm" aria-disabled={state.page <= 1} onClick={() => state.page > 1 && go(state.page - 1)}>
          <ChevronLeft aria-hidden />
          {t('pagination.previous')}
        </Button>
        <Button variant="secondary" size="sm" aria-disabled={state.page >= state.pages} onClick={() => state.page < state.pages && go(state.page + 1)}>
          {t('pagination.next')}
          <ChevronRight aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
