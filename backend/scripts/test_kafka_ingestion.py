"""
TrustGraph Kafka -> PostgreSQL ingestion smoke test.

Flow:
    Kafka
      ↓
    TrustGraphEvent validation
      ↓
    KafkaIngestionService
      ↓
    Existing PostgreSQL entities
      ↓
    Transaction row

This test does NOT:
- calculate risk
- run M2
- run ML
- call Gemini
- execute Policy
- create ground truth

The test skips unrelated older Kafka events and waits until it
receives an event matching the selected existing merchant/customer.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import session_scope
from app.kafka.consumer import KafkaEventConsumer
from app.kafka.events import TrustGraphEvent
from app.kafka.ingestion import KafkaIngestionService
from app.models import Customer, Device, Merchant, NetworkIdentifier


async def main() -> None:
    print("=" * 60)
    print("TRUSTGRAPH K5 KAFKA -> POSTGRESQL INGESTION TEST")
    print("=" * 60)

    # ---------------------------------------------------------
    # Select real entities from the existing TrustGraph database
    # ---------------------------------------------------------
    async with session_scope() as session:
        merchant = await session.scalar(
            select(Merchant).limit(1)
        )

        if merchant is None:
            raise RuntimeError("No merchant exists in the database.")

        customer = await session.scalar(
            select(Customer)
            .where(Customer.merchant_id == merchant.id)
            .limit(1)
        )

        if customer is None:
            raise RuntimeError(
                f"No customer exists for merchant {merchant.id}."
            )

        device = await session.scalar(
            select(Device).limit(1)
        )

        network = await session.scalar(
            select(NetworkIdentifier).limit(1)
        )

        print()
        print("Using existing database entities:")
        print(f"Merchant : {merchant.id}")
        print(f"Customer : {customer.id}")
        print(f"Device   : {device.id if device else None}")
        print(f"Network  : {network.id if network else None}")

    # ---------------------------------------------------------
    # Kafka event handler
    # ---------------------------------------------------------
    async def handle_event(event: TrustGraphEvent) -> None:
        # Ignore old/unrelated events already present in Kafka.
        if event.merchant_id != str(merchant.id):
            print()
            print("Skipping unrelated Kafka event:")
            print(f"  Event ID : {event.event_id}")
            print(f"  Merchant : {event.merchant_id}")
            print()
            return

        if event.customer_id != str(customer.id):
            print()
            print("Skipping unrelated Kafka event:")
            print(f"  Event ID : {event.event_id}")
            print(f"  Customer : {event.customer_id}")
            print()
            return

        print()
        print("=" * 60)
        print("KAFKA -> POSTGRESQL INGESTION")
        print("=" * 60)

        print(f"Event ID   : {event.event_id}")
        print(f"Event Type : {event.event_type}")
        print(f"Merchant   : {event.merchant_id}")
        print(f"Customer   : {event.customer_id}")
        print(f"Device     : {event.device_id}")
        print(f"Network    : {event.network_id}")
        print(f"Amount     : {event.amount}")
        print(f"Currency   : {event.currency}")
        print(f"Timestamp  : {event.timestamp}")

        # -----------------------------------------------------
        # Persist through the real ingestion service
        # -----------------------------------------------------
        async with session_scope() as session:
            service = KafkaIngestionService()

            result = await service.ingest(
                event,
                session,
            )

            print()
            print("INGESTION SUCCESSFUL")
            print(f"Event ID       : {result.event_id}")
            print(f"Transaction ID : {result.transaction_id}")
            print(f"Status         : {result.status}")
            print("=" * 60)

    # ---------------------------------------------------------
    # Kafka consumer
    # ---------------------------------------------------------
    consumer = KafkaEventConsumer(
        bootstrap_servers="kafka:9092",
        topic="trustgraph.events",
        group_id="trustgraph-k5-ingestion-final",
    )

    async with consumer:
        print()
        print("Waiting for matching Kafka payment event...")

        # The topic already contains older test events.
        # Keep consuming until we receive the event belonging
        # to the real merchant/customer selected above.
        while True:
            event = await consumer.consume_one(handle_event)

            if event is None:
                print("No valid event consumed. Continuing...")
                continue

            if (
                event.merchant_id == str(merchant.id)
                and event.customer_id == str(customer.id)
            ):
                break

        print()
        print("K5 END-TO-END INGESTION TEST COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())