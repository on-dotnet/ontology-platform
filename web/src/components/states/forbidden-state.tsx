import { ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Role } from '@/features/auth/api';

import { EmptyState } from './empty-state';

/** Says which role is required and whom to ask; never renders any of the protected data (ui-guidelines §5). */
export function ForbiddenState({ requiredRole, className }: { requiredRole: Role; className?: string }) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={ShieldAlert}
      tone="warning"
      title={t('states.forbiddenTitle')}
      description={t('states.forbiddenDescription', { role: t(`user.roles.${requiredRole}`) })}
      className={className}
    />
  );
}
