"""Verification Protocol and result type — DIP boundary.

New verification steps (e.g. a neural step) can be added by implementing
VerificationStep without changing any caller (OCP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hydramem.core.types import Relation


@dataclass
class VerificationResult:
    """Immutable result of a verification step."""

    accepted: bool
    score: float
    level: str  # e.g. "srmkg_high", "srmkg_low", "vog"
    vog_verdict: str | None = None  # "GROUNDED" / "PARTIAL" / "REJECTED"


@runtime_checkable
class VerificationStep(Protocol):
    """A single stage in the verification pipeline."""

    def verify(self, relation: Relation) -> VerificationResult:
        """Evaluate *relation* and return a result."""
        ...
