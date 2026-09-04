"""Builds the Gemini-bound `InvestigationRequest` from an M3 `ScoredCluster`.

Consumes M3 output directly -- never queries the database, never
recomputes anything M2/M3 already calculated. This keeps the
investigator strictly downstream of the deterministic pipeline.

DATA MINIMIZATION
------------------
Three things are deliberately left out of what Gemini receives, beyond
the M2/M3 pipeline already never loading customer email/display_name
in the first place (see `app/intelligence/data_loader.py` -- those
columns are never even pulled from the database):

1. Raw ID lists. `ScoredCluster.customers` / `.devices` / `.networks` /
   `.transactions` are UUID arrays -- Gemini gets only their COUNTS
   (`EntityCounts`), never the UUIDs themselves. An investigator
   reasoning about "12 customers sharing 1 device" doesn't need the 12
   customer UUIDs to do that reasoning.

2. Device/network-ID-keyed breakdowns inside the M2 signals dict
   (`device_customer_counts_in_cluster`, `..._dataset_wide`, and the
   network equivalents) -- these map specific device/network UUIDs to
   customer counts. The aggregate fields they support
   (`max_customers_per_device`, `shared_device_ratio`, etc.) already
   carry everything Gemini needs; the per-ID breakdown is stripped by
   `sanitize_signals_for_agent` below.

3. Ground truth, trivially -- `ScoredCluster` never contained it in the
   first place (M3's detection path never imports `GroundTruth`; see
   `app/risk/pipeline.py`'s docstring), so there's nothing to strip.

No passwords, API keys, payment credentials, or card numbers ever
enter this pipeline anywhere upstream, so there's nothing of that kind
to filter here either.
"""

from __future__ import annotations

from app.agent.models import (
    EntityCounts,
    InvestigationRequest,
    MLAssessment,
    RiskContext,
)
from app.risk.models import ScoredCluster

# Signal sub-fields that map specific device/network UUIDs to counts --
# stripped before sending to Gemini. The aggregate fields in the same
# signal block (num_devices, max_customers_per_device, shared_device_ratio,
# ...) are kept; only the ID-keyed dicts are removed.
_ID_KEYED_FIELDS_TO_STRIP = {
    "shared_device": ("device_customer_counts_in_cluster", "device_customer_counts_dataset_wide"),
    "shared_network": ("network_customer_counts_in_cluster", "network_customer_counts_dataset_wide"),
}


def sanitize_signals_for_agent(signals: dict) -> dict:
    """Strip device/network-ID-keyed breakdowns from the M2 signals dict.

    Returns a new dict; never mutates the input (the same `signals`
    dict is also part of `ScoredCluster` and used elsewhere).
    """
    sanitized = {}
    for signal_name, signal_values in signals.items():
        fields_to_strip = _ID_KEYED_FIELDS_TO_STRIP.get(signal_name, ())
        if not fields_to_strip:
            sanitized[signal_name] = signal_values
            continue
        sanitized[signal_name] = {
            key: value for key, value in signal_values.items() if key not in fields_to_strip
        }
    return sanitized


def build_investigation_context(
    cluster: ScoredCluster,
    ml_assessment: MLAssessment | None = None,
) -> InvestigationRequest:
    """Build the minimized, Gemini-bound request for one scored cluster."""

    return InvestigationRequest(
        cluster_id=cluster.cluster_id,
        entities=EntityCounts(
            customer_count=len(cluster.customers),
            device_count=len(cluster.devices),
            network_count=len(cluster.networks),
            transaction_count=len(cluster.transactions),
        ),
        risk=RiskContext(
            score=cluster.risk.score,
            level=cluster.risk.level,
        ),
        exposure=cluster.exposure,
        signals=sanitize_signals_for_agent(cluster.signals),
        contributors=cluster.risk.contributors,
        evidence=cluster.evidence,
        ml_assessment=ml_assessment,
    )
