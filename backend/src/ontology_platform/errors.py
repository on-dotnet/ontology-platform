"""RFC 9457 problem details for every error response."""

from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"

_HTTP_CODES = {404: "http.not_found", 405: "http.method_not_allowed"}


class AppError(Exception):
    """An expected failure that maps to a problem response with a stable code."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        # Response headers the error calls for, such as an authentication challenge.
        self.headers = dict(headers) if headers else None


def not_implemented(what: str) -> AppError:
    """A route whose shape is fixed while its implementation has not been merged yet (the M3
    skeleton, spec 003 section 16). Later batches replace every use of this."""
    return AppError(501, "http.not_implemented", f"{what} is not implemented yet.")


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationProblem(Problem):
    errors: list[ValidationIssue]


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    status: int,
    code: str,
    detail: str,
    *,
    errors: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _title(status),
        "status": status,
        "detail": detail,
        "code": code,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for the given error statuses."""
    return {
        status: {
            "model": ValidationProblem if status == 422 else Problem,
            "description": _title(status),
        }
        for status in statuses
    }


def _issue(error: Any) -> dict[str, Any]:
    # Only location, message and type: the rejected input may contain secrets.
    return {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.detail, headers=exc.headers)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, f"http.{exc.status_code}")
        return problem_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [_issue(error) for error in exc.errors()]
        return problem_response(422, "validation.failed", "Invalid request.", errors=errors)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return problem_response(500, "internal.error", "An unexpected error occurred.")

    app.openapi = _problem_openapi(app)  # type: ignore[method-assign]


def _problem_openapi(app: FastAPI) -> Callable[[], dict[str, Any]]:
    """Document error responses under application/problem+json instead of application/json."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generate()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                for status, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    if status.startswith(("4", "5")) and "application/json" in content:
                        content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")
        return schema

    return openapi
