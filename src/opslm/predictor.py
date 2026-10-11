"""The interface every system under evaluation implements."""

from __future__ import annotations

from typing import Protocol

from opslm.schema import ReconciliationInput, ReconciliationOutput


class Predictor(Protocol):
    """A system that judges the relationship between two business facts.

    Implementations record their own latency and cost in the output's ``run`` field so the
    evaluation harness can compare systems on equal terms.
    """

    name: str

    def predict(self, case: ReconciliationInput) -> ReconciliationOutput: ...
