"""Return entity.

Named `return_.py` / class `Return` (with a trailing underscore in the
module filename only) to avoid clashing with the `return` keyword.
Zero or one return per order.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Return(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "returns"

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False, default="unspecified")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    order: Mapped["Order"] = relationship(back_populates="return_")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Return(id={self.id!r}, amount={self.amount!r})"
