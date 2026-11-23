"""Login, logout and current user, plus the auth dependencies other modules reuse.

Write endpoints should depend on `CurrentUser`, `CurrentSession` or `require_role(...)`:
all of them reject unauthenticated requests (401) and, for POST/PUT/PATCH/DELETE,
requests whose X-CSRF-Token header does not match the session (403).
"""

import hmac
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from ontology_platform.db import DbSession
from ontology_platform.errors import AppError, problem_responses
from ontology_platform.modules.identity import service
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.schemas import LoginRequest, UserInfo
from ontology_platform.modules.identity.service import AuthContext, IssuedSession, Principal
from ontology_platform.settings import Settings, get_settings

SESSION_COOKIE = "op_session"
CSRF_COOKIE = "op_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

AppSettings = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def get_auth_context(
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> AuthContext | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return await service.authenticate(db, settings, token)


def verify_csrf(request: Request, context: AuthContext) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    supplied = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), context.csrf_token.encode()):
        raise AppError(403, "auth.csrf_failed", "Missing or invalid CSRF token.")


async def require_session(
    request: Request,
    context: Annotated[AuthContext | None, Depends(get_auth_context)],
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


@router.post("/login", responses=problem_responses(401, 422))
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
async def me(user: CurrentUser, response: Response) -> UserInfo:
    """The signed-in user."""
    response.headers["Cache-Control"] = "no-store"
    return _user_info(user)
