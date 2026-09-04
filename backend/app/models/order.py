"""Order entity.

Each successful transaction produces exactly one order (1:1). An order
may or may not later receive a return.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "orders"

    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    order_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="order")
    return_: Mapped["Return | None"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Order(id={self.id!r}, order_amount={self.order_amount!r})"
