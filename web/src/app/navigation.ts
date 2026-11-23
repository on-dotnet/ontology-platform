import {
  ClipboardCheck,
  Compass,
  Database,
  FileText,
  History,
  LayoutDashboard,
  Network,
  Settings,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  to: '/' | '/documents' | '/review' | '/ontology' | '/data' | '/explore' | '/releases' | '/settings';
  /** i18n key under `nav.` */
  key: 'workbench' | 'documents' | 'review' | 'ontology' | 'data' | 'explore' | 'releases' | 'settings';
  icon: LucideIcon;
}

/** The eight task-oriented sections (ui-guidelines §3); settings is pinned to the bottom of the sidebar. */
export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', key: 'workbench', icon: LayoutDashboard },
  { to: '/documents', key: 'documents', icon: FileText },
  { to: '/review', key: 'review', icon: ClipboardCheck },
  { to: '/ontology', key: 'ontology', icon: Network },
  { to: '/data', key: 'data', icon: Database },
  { to: '/explore', key: 'explore', icon: Compass },
  { to: '/releases', key: 'releases', icon: History },
  { to: '/settings', key: 'settings', icon: Settings },
];

/** The nav item a path belongs to (exact match for the workbench, prefix match for the rest). */
export function navItemForPath(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) =>
    item.to === '/' ? pathname === '/' : pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
}
