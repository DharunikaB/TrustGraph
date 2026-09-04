"""Loads observable payment/activity data from the M1 database.

CRITICAL: this module must never import `GroundTruth` or query the
`ground_truth` table. Everything downstream (graph construction,
signal extraction, clustering) operates only on what a real detection
system could actually observe. Ground truth is for evaluation only,
and evaluation happens outside this module (see M1's ground_truth
table, joined externally by `customer_id`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Customer,
    CustomerDeviceLink,
    CustomerNetworkLink,
    Device,
    NetworkIdentifier,
    Order,
    Return,
    Transaction,
)

# Columns intentionally kept minimal (no email/display_name in feature
# data -- not needed for graph/signal computation, and no reason to
# pull PII through the intelligence pipeline).
_CUSTOMER_COLUMNS = ["id", "merchant_id", "created_at"]
_DEVICE_COLUMNS = ["id", "device_fingerprint", "created_at"]
_NETWORK_COLUMNS = ["id", "ip_address", "created_at"]
_DEVICE_LINK_COLUMNS = ["customer_id", "device_id", "first_seen", "last_seen"]
_NETWORK_LINK_COLUMNS = ["customer_id", "network_id", "first_seen", "last_seen"]
_TRANSACTION_COLUMNS = ["id", "customer_id", "device_id", "network_id", "amount", "currency", "status", "created_at"]
_ORDER_COLUMNS = ["id", "transaction_id", "order_amount", "created_at"]
_RETURN_COLUMNS = ["id", "order_id", "amount", "reason", "created_at"]


@dataclass
class RawData:
    """Observable data pulled from the database, as plain DataFrames.

    Deliberately a flat bag of DataFrames rather than a graph or any
    richer structure -- graph construction is `graph_builder`'s job,
    not this module's.
    """

    customers: pd.DataFrame = field(default_factory=pd.DataFrame)
    devices: pd.DataFrame = field(default_factory=pd.DataFrame)
    networks: pd.DataFrame = field(default_factory=pd.DataFrame)
    device_links: pd.DataFrame = field(default_factory=pd.DataFrame)
    network_links: pd.DataFrame = field(default_factory=pd.DataFrame)
    transactions: pd.DataFrame = field(default_factory=pd.DataFrame)
    orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    returns: pd.DataFrame = field(default_factory=pd.DataFrame)

    def is_empty(self) -> bool:
        return len(self.customers) == 0


def _rows_to_df(rows: list, columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([{col: getattr(row, col) for col in columns} for row in rows])


async def load_raw_data(session: AsyncSession) -> RawData:
    """Fetch every table the intelligence pipeline is allowed to see.

    Uses the ORM (rather than raw SQL) so this stays consistent with
    the rest of the M1 codebase, and so it works unchanged against
    both PostgreSQL and the SQLite test database.
    """
    customers = (await session.execute(select(Customer))).scalars().all()
    devices = (await session.execute(select(Device))).scalars().all()
    networks = (await session.execute(select(NetworkIdentifier))).scalars().all()
    device_links = (await session.execute(select(CustomerDeviceLink))).scalars().all()
    network_links = (await session.execute(select(CustomerNetworkLink))).scalars().all()
    transactions = (await session.execute(select(Transaction))).scalars().all()
    orders = (await session.execute(select(Order))).scalars().all()
    returns = (await session.execute(select(Return))).scalars().all()

    transactions_df = _rows_to_df(transactions, _TRANSACTION_COLUMNS)
    if not transactions_df.empty:
        # Enum column comes back as a TransactionStatus member; normalize
        # to its string value for consistent downstream comparisons.
        transactions_df["status"] = transactions_df["status"].apply(
            lambda s: s.value if hasattr(s, "value") else s
        )

    return RawData(
        customers=_rows_to_df(customers, _CUSTOMER_COLUMNS),
        devices=_rows_to_df(devices, _DEVICE_COLUMNS),
        networks=_rows_to_df(networks, _NETWORK_COLUMNS),
        device_links=_rows_to_df(device_links, _DEVICE_LINK_COLUMNS),
        network_links=_rows_to_df(network_links, _NETWORK_LINK_COLUMNS),
        transactions=transactions_df,
        orders=_rows_to_df(orders, _ORDER_COLUMNS),
        returns=_rows_to_df(returns, _RETURN_COLUMNS),
    )
