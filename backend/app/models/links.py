"""Explicit many-to-many association entities.

These are modelled as their own tables (rather than bare SQLAlchemy
`Table` association objects) because each link carries useful metadata
-- `first_seen` / `last_seen` -- that later milestones will use as
graph edge weights/features (e.g. how long an IP has been shared, how
recently a device was reused across accounts).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerDeviceLink(UUIDPrimaryKeyMixin, Base):
    """Records that a customer has used a device."""

    __tablename__ = "customer_device_links"
    __table_args__ = (
        UniqueConstraint("customer_id", "device_id", name="uq_customer_device"),
    )

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="device_links")
    device: Mapped["Device"] = relationship(back_populates="customer_links")


class CustomerNetworkLink(UUIDPrimaryKeyMixin, Base):
    """Records that a customer has transacted from a network identifier."""

    __tablename__ = "customer_network_links"
    __table_args__ = (
        UniqueConstraint("customer_id", "network_id", name="uq_customer_network"),
    )

    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    network_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("network_identifiers.id", ondelete="CASCADE"),
        nullable=False,
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="network_links")
    network: Mapped["NetworkIdentifier"] = relationship(back_populates="customer_links")
