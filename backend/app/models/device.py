"""Device entity.

A device is identified by a stable fingerprint (hash of user agent,
platform signals, etc. in a real system -- here just an opaque
string). Multiple customers may legitimately share a device (e.g. a
family computer), so the customer<->device relationship is many-to-many
and modelled explicitly via `CustomerDeviceLink` rather than assumed to
imply abuse.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    device_fingerprint: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )

    customer_links: Mapped[list["CustomerDeviceLink"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Device(id={self.id!r}, fingerprint={self.device_fingerprint!r})"
