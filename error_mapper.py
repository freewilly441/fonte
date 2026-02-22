from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Mapping

from ui_state import UiError


@dataclass(slots=True)
class DomainError:
    code: str
    debug_message: str
    title: str
    message: str
    recovery_action: str
    field_errors: dict[str, str] | None = None


class ValidationError(Exception):
    def __init__(self, field_errors: Mapping[str, str] | None = None, message: str = "Invalid input") -> None:
        super().__init__(message)
        self.field_errors = dict(field_errors or {})


def map_exception(exc: Exception) -> DomainError:
    text = str(exc).strip() or exc.__class__.__name__
    lower = text.lower()

    if isinstance(exc, ValidationError):
        return DomainError(
            code="validation",
            debug_message=text,
            title="Please check your input",
            message="Some fields need correction before you continue.",
            recovery_action="Edit",
            field_errors=exc.field_errors,
        )

    if isinstance(exc, TimeoutError) or isinstance(exc, socket.timeout) or "timed out" in lower:
        return DomainError(
            code="network_timeout",
            debug_message=text,
            title="Request timed out",
            message="The request took too long. Please try again.",
            recovery_action="Retry",
        )

    offline_hints = (
        "network is unreachable",
        "name or service not known",
        "temporary failure in name resolution",
        "connection refused",
        "offline",
    )
    if any(hint in lower for hint in offline_hints):
        return DomainError(
            code="offline",
            debug_message=text,
            title="You appear to be offline",
            message="Check your connection and try again.",
            recovery_action="Retry",
        )

    if "401" in lower or "unauthorized" in lower:
        return DomainError(
            code="unauthorized",
            debug_message=text,
            title="Session expired",
            message="Please sign in again.",
            recovery_action="Sign in again",
        )

    if "403" in lower or "forbidden" in lower:
        return DomainError(
            code="forbidden",
            debug_message=text,
            title="Access denied",
            message="You do not have permission to do that.",
            recovery_action="Go back",
        )

    if "404" in lower or "not found" in lower:
        return DomainError(
            code="not_found",
            debug_message=text,
            title="Not found",
            message="We could not find what you requested.",
            recovery_action="Retry",
        )

    return DomainError(
        code="unknown",
        debug_message=text,
        title="Something went wrong",
        message="Please try again. If this keeps happening, use offline mode.",
        recovery_action="Retry",
    )


def to_ui_error(domain_error: DomainError) -> UiError:
    return UiError(
        title=domain_error.title,
        message=domain_error.message,
        recovery_action=domain_error.recovery_action,
        category=domain_error.code,
    )
