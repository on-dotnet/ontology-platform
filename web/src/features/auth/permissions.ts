import { useCurrentUser, type Role } from './api';

/** Roles allowed to upload documents, create ontologies and retry processing (backend `DocumentWriter`). */
const UPLOAD_ROLES: readonly Role[] = ['admin', 'editor', 'reviewer'];
/** Roles allowed to review and merge change sets, publish and activate releases. */
const REVIEW_ROLES: readonly Role[] = ['admin', 'reviewer'];

export interface Permissions {
  canUpload: boolean;
  canReview: boolean;
}

export function permissionsFor(role: Role | undefined): Permissions {
  return {
    canUpload: role !== undefined && UPLOAD_ROLES.includes(role),
    canReview: role !== undefined && REVIEW_ROLES.includes(role),
  };
}

/** What the signed-in user may change; write buttons are hidden otherwise. */
export function usePermissions(): Permissions {
  return permissionsFor(useCurrentUser()?.role);
}
