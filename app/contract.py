"""Names and strings fixed by the assignment contract. Do not rename."""

from enum import Enum


class Service(str, Enum):
    DOCTOR = "DOCTOR"
    LAB = "LAB"


class Intent(str, Enum):
    BOOK_SERVICE = "BOOK_SERVICE"
    LIST_SERVICES = "LIST_SERVICES"
    LOG_SYMPTOM = "LOG_SYMPTOM"
    CLINIC_INFO = "CLINIC_INFO"
    MEDICAL_ADVICE = "MEDICAL_ADVICE"
    EMERGENCY = "EMERGENCY"
    SMALL_TALK = "SMALL_TALK"
    UNKNOWN = "UNKNOWN"


class SafetyVerdict(str, Enum):
    EMERGENCY = "EMERGENCY"
    MEDICAL_ADVICE = "MEDICAL_ADVICE"
    SAFE = "SAFE"
