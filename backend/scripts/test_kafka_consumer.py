"""
TrustGraph Kafka consumer smoke test.

This test consumes one TrustGraph event from Kafka,
validates it against the event contract, and acknowledges it.

It does NOT invoke M2, M3, ML, Gemini, Policy, or PostgreSQL.
"""

from __future__ import annotations

import asyncio

from app.kafka.consumer import KafkaEventConsumer
from app.kafka.events import TrustGraphEvent


async def handle_event(
    event: TrustGraphEvent,
) -> None:
    """Simple smoke-test handler."""

    print()
    print("EVENT RECEIVED BY TRUSTGRAPH CONSUMER")
    print("-" * 60)
    print(f"Event ID   : {event.event_id}")
    print(f"Event Type : {event.event_type}")
    print(f"Merchant   : {event.merchant_id}")
    print(f"Customer   : {event.customer_id}")
    print(f"Device     : {event.device_id}")
    print(f"Network    : {event.network_id}")
    print(f"Amount     : {event.amount}")
    print(f"Currency   : {event.currency}")
    print(f"Timestamp  : {event.timestamp}")
    print("-" * 60)


async def main() -> None:

    print("=" * 60)
    print("TRUSTGRAPH KAFKA CONSUMER TEST")
    print("=" * 60)

    async with KafkaEventConsumer(
        bootstrap_servers="kafka:9092",
        topic="trustgraph.events",
        group_id="trustgraph-k4-test",
    ) as consumer:

        print(
            f"Bootstrap : {consumer.bootstrap_servers}"
        )

        print(
            f"Topic     : {consumer.topic}"
        )

        print(
            f"Group     : {consumer.group_id}"
        )

        print()
        print("Waiting for one Kafka event...")

        event = await consumer.consume_one(
            handle_event,
        )

        if event is None:
            print(
                "No event received."
            )
            return

        print()
        print("EVENT ACKNOWLEDGED")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())