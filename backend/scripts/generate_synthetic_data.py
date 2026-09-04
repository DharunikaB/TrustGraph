"""CLI entrypoint: generate the synthetic dataset and write it to CSV.

Usage:
    python scripts/generate_synthetic_data.py
    python scripts/generate_synthetic_data.py --seed 7 --normal 1000 \
        --shared-infra 400 --abuse 200 --out data/synthetic_run2

Run from the `backend/` directory (or with `backend/` on PYTHONPATH),
since it imports `app.core.config` for the default output directory.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.core.config import get_settings  # noqa: E402
from scripts.synthetic.builder import SyntheticDataBuilder  # noqa: E402
from scripts.synthetic.config import GeneratorConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Generate synthetic payment-abuse dataset")
    parser.add_argument("--seed", type=int, default=settings.SYNTHETIC_RANDOM_SEED)
    parser.add_argument("--merchants", type=int, default=settings.SYNTHETIC_MERCHANT_COUNT)
    parser.add_argument("--normal", type=int, default=settings.SYNTHETIC_NORMAL_CUSTOMERS)
    parser.add_argument(
        "--shared-infra", type=int, default=settings.SYNTHETIC_SHARED_INFRA_CUSTOMERS
    )
    parser.add_argument("--abuse", type=int, default=settings.SYNTHETIC_ABUSE_CUSTOMERS)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--out", type=str, default=settings.SYNTHETIC_DATA_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = GeneratorConfig(
        random_seed=args.seed,
        merchant_count=args.merchants,
        normal_customer_count=args.normal,
        shared_infra_customer_count=args.shared_infra,
        abuse_customer_count=args.abuse,
        window_days=args.window_days,
    )

    logger.info(
        "Generating synthetic data: seed=%s merchants=%s normal=%s shared_infra=%s abuse=%s",
        config.random_seed,
        config.merchant_count,
        config.normal_customer_count,
        config.shared_infra_customer_count,
        config.abuse_customer_count,
    )

    builder = SyntheticDataBuilder(config)
    frames = builder.build()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, df in frames.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("Wrote %s rows to %s", len(df), path)

    total_customers = len(frames["customers"])
    total_transactions = len(frames["transactions"])
    total_abuse = int(frames["ground_truth"]["is_abuse"].sum())
    logger.info(
        "Done. %s customers, %s transactions, %s labelled abuse (%.1f%%).",
        total_customers,
        total_transactions,
        total_abuse,
        100 * total_abuse / total_customers if total_customers else 0,
    )


if __name__ == "__main__":
    main()
