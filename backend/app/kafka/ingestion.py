"""
TrustGraph Kafka ingestion adapter.

This module bridges validated Kafka payment events into the existing
PostgreSQL transaction layer.

Architecture:

    Kafka
      ↓
    TrustGraphEvent
      ↓
    KafkaIngestionService
      ↓
    Existing PostgreSQL entities
      ↓
    Existing data_loader / M2 pipeline

This adapter intentionally does NOT:
- calculate risk
- run M2 intelligence
- run ML
- call Gemini
- execute policy
- create ground truth
- modify existing intelligence logic

Current buildathon scope:
- ingest payment events only
- reference existing merchant/customer/device/network entities
- create one Transaction row
- leave existing relationships untouched
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kafka.events import TrustGraphEvent
from app.models import (
    Customer,
    Device,
    Merchant,
    NetworkIdentifier,
    Transaction,
    TransactionStatus,
)


@dataclass(frozen=True)
class IngestionResult:
    """Result returned after processing one Kafka payment event."""

    event_id: str
    transaction_id: str
    status: str


class KafkaIngestionService:
    """Persist validated Kafka payment events into existing PostgreSQL data."""

    async def ingest(
        self,
        event: TrustGraphEvent,
        session: AsyncSession,
    ) -> IngestionResult:
        """
        Validate referenced entities and persist one transaction.

        The event must reference entities that already exist in the
        operational database. This prevents the Kafka smoke-test path
        from inventing customers, devices, networks, or merchants.

        Only payment events are persisted in this buildathon integration.
        Authentication events are accepted by the transport schema but
        are intentionally not persisted here because the current database
        has no authentication-event table.
        """

        if event.event_type != "payment":
            raise ValueError(
                f"Unsupported Kafka event type for database ingestion: "
                f"{event.event_type!r}. Only 'payment' is supported."
            )

        if event.amount is None:
            raise ValueError("Payment event must contain an amount.")

        merchant = await session.scalar(
            select(Merchant).where(Merchant.id == event.merchant_id)
        )
        if merchant is None:
            raise ValueError(
                f"Merchant {event.merchant_id!r} does not exist."
            )

        customer = await session.scalar(
            select(Customer).where(
                Customer.id == event.customer_id,
                Customer.merchant_id == event.merchant_id,
            )
        )
        if customer is None:
            raise ValueError(
                f"Customer {event.customer_id!r} does not exist for "
                f"merchant {event.merchant_id!r}."
            )

        device = None
        if event.device_id is not None:
            device = await session.scalar(
                select(Device).where(Device.id == event.device_id)
            )
            if device is None:
                raise ValueError(
                    f"Device {event.device_id!r} does not exist."
                )

        network = None
        if event.network_id is not None:
            network = await session.scalar(
                select(NetworkIdentifier).where(
                    NetworkIdentifier.id == event.network_id
                )
            )
            if network is None:
                raise ValueError(
                    f"Network {event.network_id!r} does not exist."
                )

        created_at = event.timestamp
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        transaction = Transaction(
            customer_id=customer.id,
            device_id=device.id if device is not None else None,
            network_id=network.id if network is not None else None,
            amount=event.amount,
            currency=event.currency or "INR",
            status=TransactionStatus.SUCCESS,
            created_at=created_at,
        )

        session.add(transaction)
        await session.flush()

        return IngestionResult(
            event_id=event.event_id,
            transaction_id=transaction.id,
            status="persisted",
        )