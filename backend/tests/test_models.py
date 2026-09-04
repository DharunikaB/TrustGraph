"""Tests for ORM models: relationships, constraints, cascades."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Customer,
    CustomerDeviceLink,
    Device,
    Merchant,
    NetworkIdentifier,
    Order,
    Return,
    Transaction,
    TransactionStatus,
)


def _now():
    return datetime.now(timezone.utc)


async def _make_merchant(session) -> Merchant:
    merchant = Merchant(name="Acme Retail")
    session.add(merchant)
    await session.flush()  # assign merchant.id before it's used as a FK
    return merchant


@pytest.mark.asyncio
async def test_merchant_customer_relationship(async_session):
    merchant = await _make_merchant(async_session)
    customer = Customer(merchant_id=merchant.id, email="a@example.com", display_name="Alice")
    async_session.add(customer)
    await async_session.commit()

    result = await async_session.execute(select(Customer).where(Customer.id == customer.id))
    fetched = result.scalar_one()
    assert fetched.merchant_id == merchant.id


@pytest.mark.asyncio
async def test_device_fingerprint_unique_constraint(async_session):
    d1 = Device(device_fingerprint="fingerprint-a")
    async_session.add(d1)
    await async_session.commit()

    d2 = Device(device_fingerprint="fingerprint-a")
    async_session.add(d2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_customer_device_link_unique_pair(async_session):
    merchant = await _make_merchant(async_session)
    customer = Customer(merchant_id=merchant.id, email="b@example.com", display_name="Bob")
    device = Device(device_fingerprint="shared-device")
    async_session.add_all([customer, device])
    await async_session.flush()

    link1 = CustomerDeviceLink(
        customer_id=customer.id, device_id=device.id, first_seen=_now(), last_seen=_now()
    )
    async_session.add(link1)
    await async_session.commit()

    # Same (customer, device) pair again should violate the unique constraint.
    link2 = CustomerDeviceLink(
        customer_id=customer.id, device_id=device.id, first_seen=_now(), last_seen=_now()
    )
    async_session.add(link2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_shared_device_across_multiple_customers(async_session):
    """A device CAN legitimately be linked to more than one customer."""
    merchant = await _make_merchant(async_session)
    c1 = Customer(merchant_id=merchant.id, email="c1@example.com", display_name="C1")
    c2 = Customer(merchant_id=merchant.id, email="c2@example.com", display_name="C2")
    device = Device(device_fingerprint="family-laptop")
    async_session.add_all([c1, c2, device])
    await async_session.flush()

    async_session.add_all(
        [
            CustomerDeviceLink(
                customer_id=c1.id, device_id=device.id, first_seen=_now(), last_seen=_now()
            ),
            CustomerDeviceLink(
                customer_id=c2.id, device_id=device.id, first_seen=_now(), last_seen=_now()
            ),
        ]
    )
    await async_session.commit()  # should NOT raise

    result = await async_session.execute(
        select(CustomerDeviceLink).where(CustomerDeviceLink.device_id == device.id)
    )
    links = result.scalars().all()
    assert len(links) == 2


@pytest.mark.asyncio
async def test_transaction_order_return_chain(async_session):
    merchant = await _make_merchant(async_session)
    customer = Customer(merchant_id=merchant.id, email="d@example.com", display_name="Dana")
    async_session.add(customer)
    await async_session.flush()

    transaction = Transaction(
        customer_id=customer.id,
        amount=499.00,
        currency="INR",
        status=TransactionStatus.SUCCESS,
        created_at=_now(),
    )
    async_session.add(transaction)
    await async_session.flush()

    order = Order(transaction_id=transaction.id, order_amount=499.00, created_at=_now())
    async_session.add(order)
    await async_session.flush()

    ret = Return(order_id=order.id, amount=499.00, reason="changed_mind", created_at=_now())
    async_session.add(ret)
    await async_session.commit()

    result = await async_session.execute(select(Return).where(Return.order_id == order.id))
    fetched_return = result.scalar_one()
    assert fetched_return.amount == 499.00


@pytest.mark.asyncio
async def test_order_transaction_id_is_unique(async_session):
    """An order is 1:1 with its transaction -- no double-ordering a transaction."""
    merchant = await _make_merchant(async_session)
    customer = Customer(merchant_id=merchant.id, email="e@example.com", display_name="Eve")
    async_session.add(customer)
    await async_session.flush()

    transaction = Transaction(
        customer_id=customer.id, amount=100.0, created_at=_now(), status=TransactionStatus.SUCCESS
    )
    async_session.add(transaction)
    await async_session.flush()

    async_session.add(Order(transaction_id=transaction.id, order_amount=100.0, created_at=_now()))
    await async_session.commit()

    async_session.add(Order(transaction_id=transaction.id, order_amount=100.0, created_at=_now()))
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_merchant_delete_cascades_to_customer(async_session):
    merchant = await _make_merchant(async_session)
    customer = Customer(merchant_id=merchant.id, email="f@example.com", display_name="Faye")
    async_session.add(customer)
    await async_session.commit()

    await async_session.delete(merchant)
    await async_session.commit()

    result = await async_session.execute(select(Customer).where(Customer.id == customer.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_network_identifier_unique_ip(async_session):
    ip1 = NetworkIdentifier(ip_address="10.0.0.5")
    async_session.add(ip1)
    await async_session.commit()

    ip2 = NetworkIdentifier(ip_address="10.0.0.5")
    async_session.add(ip2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()
