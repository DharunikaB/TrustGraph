"""Pydantic models for M3's output contract.

These are what M4 (the AI Investigator) will eventually consume. No
Gemini calls, no AI-generated text, no autonomous action -- just a
clean, structured, explainable object per candidate cluster.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.risk.config import RiskLevel


class Contributor(BaseModel):
    """One category's contribution to the total risk score.

    `contribution` is always <= `max_contribution` for that category,
    and the sum of every contributor's `contribution` across a cluster
    equals its total risk score (modulo rounding) -- no hidden fudge
    factors, no fake precision.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    contribution: float = Field(ge=0)
    max_contribution: float = Field(gt=0)
    evidence: str


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    level: RiskLevel
    contributors: list[Contributor]


class ExposureAssessment(BaseModel):
    """Financial context for a cluster -- deliberately NOT a fraud-loss estimate.

    Terminology is chosen carefully throughout: `transaction_value` is
    the associated transaction value (what moved through this cluster),
    `returned_value` is what was actually returned, and
    `estimated_exposure` is the returned value -- the only piece of this
    that has actually left the merchant's hands in a way a return
    represents. None of these fields should be read as "money lost to
    fraud"; a HIGH-risk cluster's transaction_value is money that moved
    through legitimate-looking transactions, not a loss figure.
    """

    model_config = ConfigDict(frozen=True)

    transaction_count: int = Field(ge=0)
    transaction_value: float = Field(ge=0)
    order_count: int = Field(ge=0)
    return_count: int = Field(ge=0)
    returned_value: float = Field(ge=0)
    estimated_exposure: float = Field(
        ge=0, description="Returned value -- the only amount that has actually reversed."
    )


class ScoredCluster(BaseModel):
    """The full M3 output for one candidate cluster -- M4's future input."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    customers: list[str]
    devices: list[str]
    networks: list[str]
    transactions: list[str]

    risk: RiskAssessment
    exposure: ExposureAssessment

    signals: dict
    evidence: list[str]
