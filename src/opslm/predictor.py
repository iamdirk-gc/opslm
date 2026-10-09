"""The interface every system under evaluation implements."""

from __future__ import annotations

from typing import Protocol

from opslm.schema import FactPair, Prediction


class Predictor(Protocol):
    """A system that judges the relationship between two business facts.

    Implementations record their own latency and cost on the returned ``Prediction``
    so the evaluation harness can compare systems on equal terms.
    """

    name: str

    def predict(self, case_id: str, pair: FactPair) -> Prediction: ...
