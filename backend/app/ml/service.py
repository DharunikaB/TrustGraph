"""Runtime ML service for TrustGraph.

Operational role: secondary behavioral validation + investigation prioritization.
The deterministic M3 risk engine remains authoritative for risk and policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib

from .features import FEATURE_NAMES, cluster_to_features

DEFAULT_THRESHOLD = 0.37
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "ml_model" / "trustgraph_gbm.joblib"


@dataclass(frozen=True)
class MLAssessment:
    cluster_id: str
    probability: float
    prediction: bool
    deterministic_prediction: bool
    disagreement: bool
    priority_rank: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "ml_probability": round(self.probability, 6),
            "ml_prediction": self.prediction,
            "deterministic_prediction": self.deterministic_prediction,
            "detector_ml_disagreement": self.disagreement,
            "priority_rank": self.priority_rank,
        }


class MLService:
    """Lazy-loading, fail-safe wrapper around the trained Gradient Boosting model."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        threshold: float = DEFAULT_THRESHOLD,
        deterministic_threshold: float = 52.0,
    ) -> None:
        self.model_path = Path(model_path)
        self.threshold = float(threshold)
        self.deterministic_threshold = float(deterministic_threshold)
        self._model: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.model_path.exists()

    def _load(self) -> Any:
        if self._model is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"ML model artifact not found: {self.model_path}")
            self._model = joblib.load(self.model_path)
            names = self._model.get("feature_names") if isinstance(self._model, dict) else None
            if names is not None and list(names) != FEATURE_NAMES:
                raise ValueError("ML model feature schema does not match TrustGraph runtime schema")
        return self._model["model"] if isinstance(self._model, dict) else self._model

    def assess(self, cluster: Any) -> MLAssessment:
        model = self._load()
        probability = float(model.predict_proba([cluster_to_features(cluster)])[0][1])
        ml_prediction = probability >= self.threshold
        deterministic_prediction = float(cluster.risk.score) >= self.deterministic_threshold
        return MLAssessment(
            cluster_id=cluster.cluster_id,
            probability=probability,
            prediction=ml_prediction,
            deterministic_prediction=deterministic_prediction,
            disagreement=ml_prediction != deterministic_prediction,
        )

    def prioritize(self, clusters: Iterable[Any]) -> list[tuple[Any, MLAssessment]]:
        ranked = [(cluster, self.assess(cluster)) for cluster in clusters]
        ranked.sort(key=lambda item: item[1].probability, reverse=True)
        return [
            (cluster, MLAssessment(**{**assessment.__dict__, "priority_rank": rank}))
            for rank, (cluster, assessment) in enumerate(ranked, start=1)
        ]
