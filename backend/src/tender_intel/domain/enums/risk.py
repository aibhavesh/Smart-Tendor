"""Risk enums: severity levels and the six risk categories (PRD FR-311)."""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskCategory(StrEnum):
    PERFORMANCE_GUARANTEE = "PERFORMANCE_GUARANTEE"
    LIQUIDATED_DAMAGES = "LIQUIDATED_DAMAGES"
    OEM_DEPENDENCY = "OEM_DEPENDENCY"
    SHORT_COMPLETION_TIME = "SHORT_COMPLETION_TIME"
    HIGH_EMD = "HIGH_EMD"
    SPECIAL_CLAUSES = "SPECIAL_CLAUSES"
