"""Maps domain exceptions to HTTP responses.

Client-facing bodies stay generic; full detail is logged server-side (Phase 13
hardening: "return generic client errors while logging full detail").
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from tender_intel.domain.exceptions import (
    AssignmentConsumedError,
    AuthenticationError,
    DomainError,
    DomainValidationError,
    DuplicateEntityError,
    EntityNotFoundError,
    ForbiddenDomainError,
    InactiveUserError,
    InvalidStatusTransitionError,
    InvalidTokenError,
    LiveUserExistsError,
    PermissionDeniedError,
)
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

# Domain exception -> (status code, stable client-facing message).
#
# LiveUserExistsError carries a deliberately *specific* message rather than the
# generic bodies used elsewhere: it is only ever raised from an ADMIN-only
# route, and the administrator cannot act on the rejection without being told
# which endpoint to use instead.
_STATUS_MAP: list[tuple[type[DomainError], int, str]] = [
    (EntityNotFoundError, status.HTTP_404_NOT_FOUND, "Resource not found."),
    (
        LiveUserExistsError,
        status.HTTP_409_CONFLICT,
        "A user account already exists for this email address. The elevation list only "
        "sets the role an account is created with; change a live user's role with "
        "PATCH /admin/users/{user_id}/role instead.",
    ),
    (
        AssignmentConsumedError,
        status.HTTP_409_CONFLICT,
        "This role assignment has already been consumed by an account and cannot be "
        "revoked. Change the live user's role with PATCH /admin/users/{user_id}/role.",
    ),
    (DuplicateEntityError, status.HTTP_409_CONFLICT, "Resource already exists."),
    (InvalidStatusTransitionError, status.HTTP_409_CONFLICT, "Invalid state transition."),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED, "Invalid credentials."),
    (InvalidTokenError, status.HTTP_401_UNAUTHORIZED, "Invalid or expired token."),
    (InactiveUserError, status.HTTP_403_FORBIDDEN, "Account is deactivated."),
    (ForbiddenDomainError, status.HTTP_403_FORBIDDEN, "Email domain is not permitted."),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN, "Insufficient permissions."),
    (DomainValidationError, 422, "Invalid request."),  # 422 Unprocessable Content
]


def register_exception_handlers(app: FastAPI) -> None:
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        for exc_type, code, message in _STATUS_MAP:
            if isinstance(exc, exc_type):
                if code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    _log.error("domain.error", error=str(exc), type=type(exc).__name__)
                else:
                    _log.info("domain.error", error=str(exc), type=type(exc).__name__)
                headers = (
                    {"WWW-Authenticate": "Bearer"} if code == status.HTTP_401_UNAUTHORIZED else None
                )
                return JSONResponse(status_code=code, content={"detail": message}, headers=headers)
        # Unmapped domain error -> treat as server-side fault.
        _log.error("domain.error.unmapped", error=str(exc), type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    app.add_exception_handler(DomainError, handle_domain_error)  # type: ignore[arg-type]
