import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { NAV_ITEMS, type NavItem } from '@/app/navigation';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/cn';

import { BrandMark, BrandName } from './brand';

interface SidebarContentProps {
  /** Icon-only rail (72px). */
  collapsed?: boolean;
  /** Called after a link is followed, e.g. to close the mobile drawer. */
  onNavigate?: () => void;
}

const mainItems = NAV_ITEMS.filter((item) => item.key !== 'settings');
const footerItems = NAV_ITEMS.filter((item) => item.key === 'settings');

export function SidebarContent({ collapsed = false, onNavigate }: SidebarContentProps) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={cn('flex h-16 shrink-0 items-center px-5', collapsed && 'justify-center px-0')}>
        <Link to="/" onClick={onNavigate} className="flex min-w-0 items-center gap-3 rounded-lg">
          <BrandMark />
          <BrandName className={cn(collapsed && 'sr-only')} />
        </Link>
      </div>
      <nav aria-label={t('nav.label')} className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pb-4 pt-2">
        <ul className="flex flex-col gap-1">
          {mainItems.map((item) => (
            <li key={item.key}>
              <SidebarLink item={item} collapsed={collapsed} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
        <ul className="mt-auto flex flex-col gap-1 border-t border-border pt-3">
          {footerItems.map((item) => (
            <li key={item.key}>
              <SidebarLink item={item} collapsed={collapsed} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

function SidebarLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: (() => void) | undefined }) {
  const { t } = useTranslation();
  const label = t(`nav.${item.key}`);
  const Icon = item.icon;
  return (
    <Tooltip content={label} side="right" disabled={!collapsed}>
      <Link
        to={item.to}
        activeOptions={{ exact: item.to === '/' }}
        onClick={onNavigate}
        className={cn(
          'flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors',
          'hover:bg-muted hover:text-foreground',
          'data-[status=active]:bg-primary-soft data-[status=active]:font-semibold data-[status=active]:text-primary-strong',
          collapsed && 'justify-center px-0',
        )}
      >
        <Icon className="size-5 shrink-0" strokeWidth={1.9} aria-hidden />
        <span className={cn('truncate', collapsed && 'sr-only')}>{label}</span>
      </Link>
    </Tooltip>
  );
}
