"""Ground-truth labels for the synthetic dataset.

This table exists ONLY for evaluating the future detector (precision,
recall, F1, false-positive cost, etc.). It is intentionally NOT
referenced by anything that builds detector features -- the detector
must learn to separate abuse from non-abuse using behavioral/graph
signals alone, never by reading this table.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroundTruthLabel(str, enum.Enum):
    NORMAL = "normal"
    LEGITIMATE_SHARED_INFRA = "legitimate_shared_infra"
    COORDINATED_ABUSE = "coordinated_abuse"


class GroundTruth(Base):
    __tablename__ = "ground_truth"

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    label: Mapped[GroundTruthLabel] = mapped_column(
        Enum(GroundTruthLabel, name="ground_truth_label"), nullable=False
    )
    cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_abuse: Mapped[bool] = mapped_column(Boolean, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"GroundTruth(customer_id={self.customer_id!r}, label={self.label!r})"
