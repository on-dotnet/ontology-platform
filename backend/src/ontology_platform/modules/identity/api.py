"""Login, logout and current user, plus the auth dependencies other modules reuse.

Write endpoints should depend on `CurrentUser`, `CurrentSession` or `require_role(...)`:
all of them reject unauthenticated requests (401) and, for POST/PUT/PATCH/DELETE,
requests whose X-CSRF-Token header does not match the session (403).

Access tokens (spec 003, section 4): a request with `Authorization: Bearer ...` is
authenticated by the token alone, never by its cookies, and an invalid token is 401
`auth.invalid_token`. Tokens are refused by default: `CurrentUser`, `CurrentSession` and
`require_role(...)` answer a valid token with 403 `auth.token_not_allowed`. Only routes that
depend on `require_scope(...)` (or `AnyPrincipal`) accept one, and token requests skip CSRF.
"""

import hmac
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from ontology_platform.db import DbSession
from ontology_platform.errors import AppError, problem_responses
from ontology_platform.modules.identity import schemas, service, tokens
from ontology_platform.modules.identity.models import Role, TokenScope
from ontology_platform.modules.identity.schemas import LoginRequest, UserInfo
from ontology_platform.modules.identity.service import AuthContext, IssuedSession, Principal
from ontology_platform.modules.identity.tokens import TokenContext
from ontology_platform.settings import Settings, get_settings

SESSION_COOKIE = "op_session"
CSRF_COOKIE = "op_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BEARER_SCHEME = "bearer"

AppSettings = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def bearer_token(request: Request) -> str | None:
    """The credentials of an `Authorization: Bearer` header ("" when empty); None without one.
    Other schemes are not ours and are ignored."""
    parts = request.headers.get("authorization", "").split(maxsplit=1)
    if not parts or parts[0].lower() != BEARER_SCHEME:
        return None
    return parts[1].strip() if len(parts) > 1 else ""


async def get_token_context(request: Request, db: DbSession) -> TokenContext | None:
    """The access token the request carries, if any. An invalid one is 401, with no fallback
    to the session cookie."""
    token = bearer_token(request)
    if token is None:
        return None
    return await tokens.authenticate(db, token, ip=client_ip(request))


OptionalToken = Annotated[TokenContext | None, Depends(get_token_context)]


async def get_auth_context(
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> AuthContext | None:
    # A request that carries a token is authenticated by the token only.
    if bearer_token(request) is not None:
        return None
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return await service.authenticate(db, settings, token)


OptionalSession = Annotated[AuthContext | None, Depends(get_auth_context)]


def verify_csrf(request: Request, context: AuthContext) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    supplied = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), context.csrf_token.encode()):
        raise AppError(403, "auth.csrf_failed", "Missing or invalid CSRF token.")


async def refuse_tokens(token: OptionalToken) -> None:
    """Routes are closed to access tokens unless they say otherwise (spec 003, section 4)."""
    if token is not None:
        raise AppError(
            403, "auth.token_not_allowed", "This endpoint does not accept access tokens."
        )


async def require_session(
    request: Request,
    _: Annotated[None, Depends(refuse_tokens)],
    context: OptionalSession,
) -> AuthContext:
    if context is None:
        raise AppError(401, "auth.not_authenticated", "Authentication required.")
    verify_csrf(request, context)
    return context


CurrentSession = Annotated[AuthContext, Depends(require_session)]


async def require_user(context: CurrentSession) -> Principal:
    return context.principal


CurrentUser = Annotated[Principal, Depends(require_user)]


def require_role(*roles: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory: the current user must hold one of `roles`."""
    allowed = frozenset(roles)

    async def check_role(user: CurrentUser) -> Principal:
        if user.role not in allowed:
            raise AppError(403, "auth.forbidden", "Insufficient role.")
        return user

    return check_role


def _session_principal(request: Request, context: AuthContext | None) -> Principal:
    if context is None:
        raise AppError(401, "auth.not_authenticated", "Authentication required.")
    verify_csrf(request, context)
    return context.principal


def require_scope(scope: TokenScope) -> Callable[..., Awaitable[Principal]]:
    """Dependency factory for the few routes that also accept an access token holding `scope`
    (spec 003, section 4; the appendix lists them). Every other route refuses tokens.

    A cookie session is checked as usual, CSRF included. A token must hold `scope` after it is
    cut down to what its owner's current role allows."""

    async def check_scope(
        request: Request, token: OptionalToken, context: OptionalSession
    ) -> Principal:
        if token is None:
            return _session_principal(request, context)
        if scope not in token.scopes:
            raise AppError(403, "auth.insufficient_scope", "The access token lacks a scope.")
        return token.principal

    return check_scope


async def require_principal(
    request: Request, token: OptionalToken, context: OptionalSession
) -> Principal:
    """A cookie session or any valid access token, whatever its scopes: only for the routes the
    appendix opens to every token (`/api/auth/me`)."""
    if token is not None:
        return token.principal
    return _session_principal(request, context)


AnyPrincipal = Annotated[Principal, Depends(require_principal)]


def _set_session_cookies(response: Response, settings: Settings, issued: IssuedSession) -> None:
    max_age = settings.session_absolute_days * 24 * 3600
    secure = settings.secure_cookies
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    secure = settings.secure_cookies
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="lax")


def _user_info(principal: Principal) -> UserInfo:
    return UserInfo(
        id=principal.id,
        username=principal.username,
        display_name=principal.display_name,
        role=principal.role,
    )


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/login",
    dependencies=[Depends(refuse_tokens)],
    responses=problem_responses(401, 422),
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> UserInfo:
    """Sign in. Replaces the session the request came with, if any, and sets the HttpOnly
    session cookie and the script-readable CSRF cookie.
    """
    principal, issued = await service.login(
        db,
        settings,
        username=body.username,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        previous_token=request.cookies.get(SESSION_COOKIE),
    )
    _set_session_cookies(response, settings, issued)
    response.headers["Cache-Control"] = "no-store"
    return _user_info(principal)


@router.post("/logout", status_code=204, responses=problem_responses(401, 403))
async def logout(
    request: Request,
    response: Response,
    context: CurrentSession,
    db: DbSession,
    settings: AppSettings,
) -> None:
    """End the current session. Requires the X-CSRF-Token header."""
    await service.logout(db, context, ip=client_ip(request))
    _clear_session_cookies(response, settings)


@router.get("/me", responses=problem_responses(401))
async def me(user: AnyPrincipal, response: Response) -> UserInfo:
    """The signed-in user, or the owner of the access token."""
    response.headers["Cache-Control"] = "no-store"
    return _user_info(user)


# ---------- access tokens (spec 003 §4) ----------
# Managed with a cookie session only: a token can never list, create or revoke tokens.


@router.get("/tokens", responses=problem_responses(401, 403, 422))
async def list_tokens(
    user: CurrentUser,
    db: DbSession,
    response: Response,
    owner: Annotated[tokens.TokenOwnerFilter, Query()] = "me",
) -> list[schemas.AccessToken]:
    """The user's access tokens; `owner=all` lists everyone's and needs the admin role. Neither
    the tokens themselves nor their hashes are ever returned."""
    response.headers["Cache-Control"] = "no-store"
    return await tokens.list_tokens(db, actor=user, owner=owner)


@router.post("/tokens", status_code=201, responses=problem_responses(401, 403, 409, 422))
async def create_token(
    body: schemas.AccessTokenCreate,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> schemas.AccessTokenCreated:
    """Create an access token. This response is the only time the token is shown."""
    response.headers["Cache-Control"] = "no-store"
    return await tokens.create_token(db, body, actor=user, ip=client_ip(request))


@router.delete("/tokens/{id}", status_code=204, responses=problem_responses(401, 403, 404, 422))
async def revoke_token(id: UUID, request: Request, user: CurrentUser, db: DbSession) -> None:
    """Revoke a token at once: one's own, or anyone's for an admin."""
    await tokens.revoke_token(db, id, actor=user, ip=client_ip(request))
