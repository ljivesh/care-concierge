"""Names and strings fixed by the assignment contract. Do not rename."""

from enum import Enum


class Service(str, Enum):
    DOCTOR = "DOCTOR"
    LAB = "LAB"
