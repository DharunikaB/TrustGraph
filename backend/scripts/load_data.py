"""Load a generated synthetic dataset (CSV files) into PostgreSQL.

Usage:
    python scripts/load_data.py --input data/synthetic
    python scripts/load_data.py --input data/synthetic --reset

`--reset` drops and recreates all tables first -- useful for repeated
local runs, never something you'd want against a real deployment.

Loading order matters and follows the FK dependency chain:
merchants -> customers -> devices/ips -> links -> transactions ->
orders -> returns. Ground truth is loaded last into its own table,
kept separate from the operational schema since it must never be
visible to the future detector as a feature.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.db.init_db import drop_models, init_models  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models import (  # noqa: E402
    Customer,
    CustomerDeviceLink,
    CustomerNetworkLink,
    Device,
    GroundTruth,
    Merchant,
    NetworkIdentifier,
    Order,
    Return,
    Transaction,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def _read_csv(input_dir: Path, name: str) -> pd.DataFrame:
    path = input_dir / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Expected {path} -- did you run scripts/generate_synthetic_data.py first?"
        )
    df = pd.read_csv(path)
    # Parse timestamp columns explicitly with `pd.to_datetime` rather than
    # relying on `read_csv(parse_dates=...)`: when a column mixes
    # second-precision and microsecond-precision timestamps (which our
    # generator's output does), pandas' parser silently falls back to
    # plain strings instead of raising -- asyncpg then rejects them at
    # insert time with a much less obvious error.
    for col in _TIMESTAMP_COLUMNS.get(name, []):
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601")
    return df


_TIMESTAMP_COLUMNS = {
    "merchants": ["created_at"],
    "customers": ["created_at"],
    "devices": ["created_at"],
    "ips": ["created_at"],
    "customer_device_links": ["first_seen", "last_seen"],
    "customer_network_links": ["first_seen", "last_seen"],
    "transactions": ["created_at"],
    "orders": ["created_at"],
    "returns": ["created_at"],
}


async def _bulk_insert(session, model, records: list[dict]) -> None:
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        await session.execute(model.__table__.insert(), batch)


async def load(input_dir: Path, reset: bool) -> None:
    if reset:
        logger.info("Dropping and recreating all tables...")
        await drop_models()
        await init_models()
    else:
        await init_models()

    merchants = _read_csv(input_dir, "merchants")
    customers = _read_csv(input_dir, "customers")
    devices = _read_csv(input_dir, "devices")
    ips = _read_csv(input_dir, "ips")
    device_links = _read_csv(input_dir, "customer_device_links")
    network_links = _read_csv(input_dir, "customer_network_links")
    transactions = _read_csv(input_dir, "transactions")
    orders = _read_csv(input_dir, "orders")
    returns = _read_csv(input_dir, "returns")
    ground_truth = _read_csv(input_dir, "ground_truth")

    # Basic referential-integrity sanity checks before touching the DB.
    _validate_foreign_keys(customers, "merchant_id", merchants, "id", "customers -> merchants")
    _validate_foreign_keys(device_links, "customer_id", customers, "id", "device_links -> customers")
    _validate_foreign_keys(device_links, "device_id", devices, "id", "device_links -> devices")
    _validate_foreign_keys(network_links, "customer_id", customers, "id", "network_links -> customers")
    _validate_foreign_keys(network_links, "network_id", ips, "id", "network_links -> ips")
    _validate_foreign_keys(transactions, "customer_id", customers, "id", "transactions -> customers")
    _validate_foreign_keys(orders, "transaction_id", transactions, "id", "orders -> transactions")
    _validate_foreign_keys(returns, "order_id", orders, "id", "returns -> orders")
    _validate_foreign_keys(ground_truth, "customer_id", customers, "id", "ground_truth -> customers")

    async with session_scope() as session:
        logger.info("Loading %s merchants...", len(merchants))
        await _bulk_insert(session, Merchant, merchants.to_dict("records"))

        logger.info("Loading %s customers...", len(customers))
        await _bulk_insert(session, Customer, customers.to_dict("records"))

        logger.info("Loading %s devices...", len(devices))
        await _bulk_insert(session, Device, devices.to_dict("records"))

        logger.info("Loading %s network identifiers...", len(ips))
        await _bulk_insert(session, NetworkIdentifier, ips.to_dict("records"))

        logger.info("Loading %s customer-device links...", len(device_links))
        await _bulk_insert(session, CustomerDeviceLink, device_links.to_dict("records"))

        logger.info("Loading %s customer-network links...", len(network_links))
        await _bulk_insert(session, CustomerNetworkLink, network_links.to_dict("records"))

        logger.info("Loading %s transactions...", len(transactions))
        await _bulk_insert(session, Transaction, transactions.to_dict("records"))

        logger.info("Loading %s orders...", len(orders))
        await _bulk_insert(session, Order, orders.to_dict("records"))

        logger.info("Loading %s returns...", len(returns))
        await _bulk_insert(session, Return, returns.to_dict("records"))

        logger.info("Loading %s ground-truth rows...", len(ground_truth))
        gt_records = ground_truth.where(pd.notnull(ground_truth), None).to_dict("records")
        await _bulk_insert(session, GroundTruth, gt_records)

    logger.info("Load complete.")


def _validate_foreign_keys(
    child_df: pd.DataFrame,
    child_col: str,
    parent_df: pd.DataFrame,
    parent_col: str,
    description: str,
) -> None:
    valid_ids = set(parent_df[parent_col])
    child_ids = child_df[child_col].dropna()
    orphans = child_ids[~child_ids.isin(valid_ids)]
    if len(orphans) > 0:
        raise ValueError(
            f"Referential integrity check failed for {description}: "
            f"{len(orphans)} rows reference an id that doesn't exist "
            f"(e.g. {orphans.iloc[0]!r})."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load synthetic dataset CSVs into PostgreSQL")
    parser.add_argument("--input", type=str, default="data/synthetic")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before loading (local/dev only).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input)
    if not input_dir.exists():
        raise SystemExit(
            f"Input directory {input_dir} does not exist. "
            "Run scripts/generate_synthetic_data.py first."
        )
    asyncio.run(load(input_dir, reset=args.reset))


if __name__ == "__main__":
    main()
