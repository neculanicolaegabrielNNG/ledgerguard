from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


# ————————————————————————————————————————

def not_found(entity: str, identifier: str) -> DomainError:
    return DomainError(
        f"{entity}_not_found", f"Resursa '{entity}' nu a fost găsită.", 404, {"id": identifier}
    )


# ————————————————————————————————————————

def conflict(code: str, message: str, details: dict[str, Any] | None = None) -> DomainError:
    return DomainError(code, message, 409, details)


# ————————————————————————————————————————

def invalid(code: str, message: str, details: dict[str, Any] | None = None) -> DomainError:
    return DomainError(code, message, 422, details)


# ————————————————————————————————————————

def forbidden(message: str = "Nu ai permisiunea pentru această operațiune.") -> DomainError:
    return DomainError("forbidden", message, 403)


# ————————————————————————————————————————

def unauthorized(message: str = "Autentificare necesară sau invalidă.") -> DomainError:
    return DomainError("unauthorized", message, 401)


# ————————————————————————————————————————

def rate_limited() -> DomainError:
    return DomainError("rate_limited", "Prea multe cereri. Încearcă mai târziu.", 429)


# ————————————————————————————————————————

def bad_request(code: str, message: str, details: dict[str, Any] | None = None) -> DomainError:
    return DomainError(code, message, 400, details)
