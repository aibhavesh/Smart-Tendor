"""Domain exceptions — framework-free, mapped to HTTP status in the API layer."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level errors."""


class EntityNotFoundError(DomainError):
    def __init__(self, entity: str, identifier: object) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier!r}")


class DuplicateEntityError(DomainError):
    """A uniqueness constraint would be violated (e.g. duplicate tender number)."""

    def __init__(self, entity: str, field: str, value: object) -> None:
        self.entity = entity
        self.field = field
        self.value = value
        super().__init__(f"{entity} with {field}={value!r} already exists")


class InvalidStatusTransitionError(DomainError):
    def __init__(self, entity: str, current: object, target: object) -> None:
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(f"{entity}: cannot transition {current} -> {target}")


class DomainValidationError(DomainError):
    """A domain invariant was violated."""


class PermissionDeniedError(DomainError):
    """The actor lacks the required role for an action."""


class AuthenticationError(DomainError):
    """Invalid credentials or an unauthenticated request."""


class InactiveUserError(DomainError):
    """The account exists but has been deactivated."""


class InvalidTokenError(DomainError):
    """A JWT is malformed, expired, revoked or of the wrong type."""


class ForbiddenDomainError(DomainError):
    """The email address is not on an allowed organisation domain.

    Raised by the admission gate *before* any User row is created, so a
    rejected sign-in never leaves a partial account behind.
    """


class AssignmentConsumedError(DomainError):
    """An already-consumed role assignment cannot be revoked.

    The account it provisioned exists and carries its own role now, so removing
    the row would undo nothing and erase the record of what happened.
    """


class LiveUserExistsError(DomainError):
    """A role assignment was requested for an email that already has an account.

    The elevation list governs the role an account is *born* with. Once the
    account exists the list no longer applies to it, so the caller must use the
    role-change endpoint (FR-602) instead.
    """


__all__ = [
    "AssignmentConsumedError",
    "AuthenticationError",
    "DomainError",
    "DomainValidationError",
    "DuplicateEntityError",
    "EntityNotFoundError",
    "ForbiddenDomainError",
    "InactiveUserError",
    "InvalidStatusTransitionError",
    "InvalidTokenError",
    "LiveUserExistsError",
    "PermissionDeniedError",
]
