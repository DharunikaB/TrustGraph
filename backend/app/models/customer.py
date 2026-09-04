"""Customer entity.

Belongs to exactly one merchant. Connects outward to devices, network
identifiers and transactions -- these relationships are the raw
material the later graph/detection milestones will operate on.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_merchant_id", "merchant_id"),
    )

    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")

    device_links: Mapped[list["CustomerDeviceLink"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    network_links: Mapped[list["CustomerNetworkLink"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Customer(id={self.id!r}, email={self.email!r})"
