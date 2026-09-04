"""Network identifier entity (IP address / network fingerprint).

Same reasoning as `Device`: many customers can legitimately share an
IP (offices, shared Wi-Fi, campuses, mobile carriers behind NAT), so
this is a many-to-many relationship via `CustomerNetworkLink`, never a
direct abuse signal on its own.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class NetworkIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "network_identifiers"

    ip_address: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    customer_links: Mapped[list["CustomerNetworkLink"]] = relationship(
        back_populates="network", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"NetworkIdentifier(id={self.id!r}, ip_address={self.ip_address!r})"
