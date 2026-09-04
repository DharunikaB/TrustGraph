"""Transaction entity.

Each transaction is tied to exactly one customer, and optionally to
the device and network identifier it was made from (nullable because
not every real-world transaction has clean device/network telemetry).
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TransactionStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class Transaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_customer_id", "customer_id"),
        Index("ix_transactions_created_at", "created_at"),
    )

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    network_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("network_identifiers.id", ondelete="SET NULL"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.SUCCESS,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="transactions")
    device: Mapped["Device | None"] = relationship()
    network: Mapped["NetworkIdentifier | None"] = relationship()
    order: Mapped["Order | None"] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Transaction(id={self.id!r}, amount={self.amount!r}, status={self.status!r})"
