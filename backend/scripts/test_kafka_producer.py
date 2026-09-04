"""
TrustGraph Kafka producer smoke test.

Publishes a payment event using real entities from the TrustGraph database.
The script itself does not access PostgreSQL; IDs are supplied explicitly
for the Kafka -> PostgreSQL ingestion test.

It does NOT invoke M2, M3, ML, Gemini, Policy, or modify PostgreSQL.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.kafka.events import TrustGraphEvent
from app.kafka.producer import KafkaEventProducer


async def main() -> None:
    event = TrustGraphEvent(
        event_id="k5-real-001",
        event_type="payment",
        merchant_id="8826d916-cdfb-41c6-81ff-91a761565a70",
        customer_id="667840ed-06ce-44c8-b158-d4a4b6a00467",
        device_id="1e512c3a-2238-4617-8344-f98dafbf4ce3",
        network_id="10c2b4a1-f573-4c2a-8309-12c21f7955b3",
        amount=1299.0,
        currency="INR",
        timestamp=datetime.now(timezone.utc),
    )

    print("=" * 60)
    print("TRUSTGRAPH K5 KAFKA PRODUCER TEST")
    print("=" * 60)

    print(f"Event ID   : {event.event_id}")
    print(f"Merchant   : {event.merchant_id}")
    print(f"Customer   : {event.customer_id}")
    print(f"Device     : {event.device_id}")
    print(f"Network    : {event.network_id}")
    print(f"Amount     : {event.amount} {event.currency}")

    async with KafkaEventProducer(
        bootstrap_servers="kafka:9092",
        topic="trustgraph.events",
    ) as producer:
        print()
        print("Connecting to Kafka...")
        print(f"Bootstrap  : {producer.bootstrap_servers}")
        print(f"Topic      : {producer.topic}")

        await producer.publish(event)

        print()
        print("REAL K5 EVENT PUBLISHED SUCCESSFULLY")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())