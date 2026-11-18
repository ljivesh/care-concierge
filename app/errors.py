"""One error type for everything we refuse or fail at, with a sentence a patient can read."""

from enum import Enum

from sqlalchemy.exc import IntegrityError


class ErrorCode(str, Enum):
    # the request does not make sense
    PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
    UNKNOWN_SUBTYPE = "UNKNOWN_SUBTYPE"
    NOT_OFFERED_AT_SOCIETY = "NOT_OFFERED_AT_SOCIETY"
    NOT_A_SLOT = "NOT_A_SLOT"
    INVALID_SEVERITY = "INVALID_SEVERITY"
    # the database said no
    SLOT_TAKEN = "SLOT_TAKEN"
    REQUEST_ID_REUSED = "REQUEST_ID_REUSED"
    # the tool call itself went wrong
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_FAILED = "TOOL_FAILED"


class ConciergeError(Exception):
    def __init__(self, code: ErrorCode, message: str, suggestions: list[dict] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions or []


def violated_constraint(exc: IntegrityError) -> str | None:
    """Postgres reports the name of the constraint that rejected a write."""
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
