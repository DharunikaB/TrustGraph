"""
FastAPI application entrypoint.

TrustGraph exposes the operational intelligence API for the payment-abuse
detection system.

Kafka is an optional event-ingestion layer. Kafka events are validated and
persisted into the existing PostgreSQL transaction layer, while the core
TrustGraph intelligence pipeline remains independent of Kafka.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session, session_scope
from app.models import Customer, Merchant, Transaction

from app.intelligence.pipeline import run_pipeline_async
from app.intelligence.data_loader import load_raw_data
from app.intelligence.graph_builder import build_relationship_graph
from app.intelligence.clustering import find_candidate_clusters
from app.intelligence.config import IntelligenceConfig

from app.risk.pipeline import run_risk_pipeline_async
from app.risk.evaluation import evaluate, load_ground_truth

from app.agent.pipeline import investigate_cluster
from app.workflow import respond_to_cluster

from app.policy.engine import policy_decision_store
from app.actions.sandbox import sandbox_executor
from app.audit.service import audit_service

from app.kafka.consumer import KafkaEventConsumer
from app.kafka.ingestion import KafkaIngestionService


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI application lifespan.

    Kafka is connected as an optional background ingestion layer.

    Flow:
        Kafka
          ↓
        KafkaEventConsumer
          ↓
        TrustGraphEvent validation
          ↓
        KafkaIngestionService
          ↓
        PostgreSQL Transaction

    The existing TrustGraph intelligence, risk, ML, Gemini, policy and
    sandbox-action pipelines remain independent of Kafka.
    """

    kafka_consumer = KafkaEventConsumer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_TOPIC,
        group_id=settings.KAFKA_CONSUMER_GROUP,
    )

    ingestion_service = KafkaIngestionService()

    async def handle_kafka_event(event):
        """
        Persist one validated Kafka payment event.

        session_scope() commits only after successful ingestion and rolls
        back automatically if ingestion raises an exception.
        """
        async with session_scope() as session:
            result = await ingestion_service.ingest(
                event,
                session,
            )

        print(
            f"KAFKA EVENT INGESTED: "
            f"{result.event_id} -> {result.transaction_id}"
        )

    async def consume_loop():
        """
        Continuously consume Kafka events while the API is running.
        """
        while True:
            try:
                await kafka_consumer.consume_one(
                    handle_kafka_event
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                print(
                    "KAFKA CONSUMER ERROR:",
                    exc,
                )

    try:
        await kafka_consumer.start()

        consumer_task = asyncio.create_task(
            consume_loop()
        )

        app.state.kafka_consumer = kafka_consumer
        app.state.kafka_consumer_task = consumer_task

        yield

    finally:
        consumer_task.cancel()

        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

        await kafka_consumer.stop()


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "TrustGraph operational intelligence service for detecting "
        "coordinated payment abuse using graph relationships, behavioral "
        "signals, deterministic risk scoring, ML validation, AI "
        "investigation, policy decisions and sandboxed actions."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# M6: the React frontend (Vite dev server, typically localhost:5173) runs
# on a different origin than the API -- without CORS the browser blocks
# every request. Restricted to local dev origins only; this is a
# buildathon demo app, not a public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Basic liveness check -- does not touch the database."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/db", tags=["system"])
async def health_db(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Confirms the API can actually reach PostgreSQL."""
    result = await session.execute(
        select(func.count()).select_from(Merchant)
    )
    merchant_count = result.scalar_one()

    return {
        "status": "ok",
        "merchant_count": merchant_count,
    }


@app.get("/stats", tags=["system"])
async def stats(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Row counts for the core entities."""
    merchant_count = (
        await session.execute(
            select(func.count()).select_from(Merchant)
        )
    ).scalar_one()

    customer_count = (
        await session.execute(
            select(func.count()).select_from(Customer)
        )
    ).scalar_one()

    transaction_count = (
        await session.execute(
            select(func.count()).select_from(Transaction)
        )
    ).scalar_one()

    return {
        "merchants": merchant_count,
        "customers": customer_count,
        "transactions": transaction_count,
    }


@app.get("/intelligence/clusters", tags=["intelligence"])
async def intelligence_clusters(
    limit: int = Query(default=20, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run the full graph + behavioral candidate detection pipeline."""
    results = await run_pipeline_async(session)

    return {
        "total_candidate_clusters": len(results),
        "returned": min(limit, len(results)),
        "clusters": results[:limit],
    }


@app.get(
    "/intelligence/clusters/{cluster_id}/graph",
    tags=["intelligence"],
)
async def cluster_graph(
    cluster_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return raw relationship graph data for one candidate cluster."""
    data = await load_raw_data(session)

    graph = build_relationship_graph(data)

    clusters = find_candidate_clusters(
        graph,
        IntelligenceConfig(),
    )

    cluster = next(
        (
            c
            for c in clusters
            if c.cluster_id == cluster_id
        ),
        None,
    )

    if cluster is None:
        return {
            "error": (
                f"No candidate cluster with id "
                f"{cluster_id!r} in the current run."
            )
        }

    node_ids = (
        [
            f"customer:{cid}"
            for cid in cluster.customer_ids
        ]
        + [
            f"device:{did}"
            for did in cluster.device_ids
        ]
        + [
            f"network:{nid}"
            for nid in cluster.network_ids
        ]
    )

    subgraph = graph.subgraph(node_ids)

    nodes = [
        {
            "id": n,
            "type": subgraph.nodes[n]["type"],
            "entity_id": subgraph.nodes[n]["entity_id"],
        }
        for n in subgraph.nodes
    ]

    edges = [
        {
            "source": u,
            "target": v,
            "type": edata.get("type"),
        }
        for u, v, edata in subgraph.edges(data=True)
    ]

    return {
        "cluster_id": cluster_id,
        "nodes": nodes,
        "edges": edges,
    }


@app.get("/risk/clusters", tags=["risk"])
async def risk_clusters(
    limit: int = Query(default=20, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run M2 graph intelligence followed by M3 risk scoring."""
    scored = await run_risk_pipeline_async(session)

    scored_sorted = sorted(
        scored,
        key=lambda c: c.risk.score,
        reverse=True,
    )

    return {
        "total_candidate_clusters": len(scored_sorted),
        "returned": min(limit, len(scored_sorted)),
        "clusters": [
            c.model_dump()
            for c in scored_sorted[:limit]
        ],
    }


@app.get(
    "/risk/clusters/{cluster_id}",
    tags=["risk"],
)
async def risk_cluster_detail(
    cluster_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return one risk-scored cluster."""
    scored = await run_risk_pipeline_async(session)

    for cluster in scored:
        if cluster.cluster_id == cluster_id:
            return cluster.model_dump()

    return {
        "error": (
            f"No candidate cluster with id "
            f"{cluster_id!r} in the current run."
        )
    }


@app.get("/risk/evaluation", tags=["risk"])
async def risk_evaluation(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Evaluate the current detection path against synthetic ground truth.

    Ground truth is only accessed here.
    """
    scored = await run_risk_pipeline_async(session)
    ground_truth = await load_ground_truth(session)

    return evaluate(
        scored,
        ground_truth,
    )


@app.post(
    "/agent/investigate/{cluster_id}",
    tags=["agent"],
)
async def agent_investigate(
    cluster_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run the AI Investigator against one candidate cluster."""
    result = await investigate_cluster(
        cluster_id,
        session,
    )

    if result is None:
        return {
            "error": (
                f"No candidate cluster with id "
                f"{cluster_id!r} in the current run."
            )
        }

    return result.model_dump(mode="json")


@app.post(
    "/agent/respond/{cluster_id}",
    tags=["agent"],
)
async def agent_respond(
    cluster_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Run the complete autonomous workflow:

        investigate -> policy -> sandbox action -> audit

    Real payment/customer actions are never executed.
    """
    result = await respond_to_cluster(
        cluster_id,
        session,
    )

    if result is None:
        return {
            "error": (
                f"No candidate cluster with id "
                f"{cluster_id!r} in the current run."
            )
        }

    return result.model_dump(mode="json")


@app.get(
    "/policy/decisions/{decision_id}",
    tags=["policy"],
)
async def get_policy_decision(
    decision_id: str,
) -> dict:
    """Look up a previously made policy decision."""
    decision = policy_decision_store.get(
        decision_id
    )

    if decision is None:
        return {
            "error": (
                f"No policy decision with id "
                f"{decision_id!r}."
            )
        }

    return decision.model_dump(mode="json")


@app.get(
    "/actions/{action_id}",
    tags=["actions"],
)
async def get_action_result(
    action_id: str,
) -> dict:
    """Look up a previously executed simulated action."""
    result = sandbox_executor.get(
        action_id
    )

    if result is None:
        return {
            "error": (
                f"No action with id "
                f"{action_id!r}."
            )
        }

    return result.model_dump(mode="json")


@app.get(
    "/audit/{cluster_id}",
    tags=["audit"],
)
async def get_audit_trail(
    cluster_id: str,
) -> dict:
    """Return the audit trail for one cluster."""
    events = audit_service.get_for_cluster(
        cluster_id
    )

    return {
        "cluster_id": cluster_id,
        "event_count": len(events),
        "events": [
            e.model_dump(mode="json")
            for e in events
        ],
    }