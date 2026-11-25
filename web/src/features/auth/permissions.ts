import { useCurrentUser, type Role } from './api';

/** Roles allowed to upload documents, create ontologies and retry processing (backend `DocumentWriter`). */
const UPLOAD_ROLES: readonly Role[] = ['admin', 'editor', 'reviewer'];
/** Roles allowed to review and merge change sets, publish and activate releases. */
const REVIEW_ROLES: readonly Role[] = ['admin', 'reviewer'];
/** Roles allowed to create, change and archive data sources (spec 003, section 13). */
const DATA_SOURCE_ADMIN_ROLES: readonly Role[] = ['admin'];
/**
 * Roles allowed to browse a data source's catalog, ask for AI binding suggestions, edit bindings
 * and give an access token the `changes:propose` scope (spec 003, section 13).
 */
const CATALOG_ROLES: readonly Role[] = ['admin', 'editor', 'reviewer'];

export interface Permissions {
  canUpload: boolean;
  canReview: boolean;
  canManageDataSources: boolean;
  canBrowseCatalog: boolean;
  canEditBindings: boolean;
  canProposeViaMcp: boolean;
}

export function permissionsFor(role: Role | undefined): Permissions {
  const has = (roles: readonly Role[]) => role !== undefined && roles.includes(role);
  return {
    canUpload: has(UPLOAD_ROLES),
    canReview: has(REVIEW_ROLES),
    canManageDataSources: has(DATA_SOURCE_ADMIN_ROLES),
    canBrowseCatalog: has(CATALOG_ROLES),
    canEditBindings: has(CATALOG_ROLES),
    canProposeViaMcp: has(CATALOG_ROLES),
  };
}

/** What the signed-in user may change; write buttons are hidden otherwise. */
export function usePermissions(): Permissions {
  return permissionsFor(useCurrentUser()?.role);
}
