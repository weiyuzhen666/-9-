"""Weighted Reciprocal Rank Fusion (RRF) -- S1 extension.

Fuses candidate lists from multiple base algorithms (popular / content /
itemcf / als / cold_start). Per the course requirement, fusion operates on
*ranks*, never on raw scores of different scales:

    score(d) = sum_r( w_r / (k + rank_r(d)) ),  k = 60

Each output item carries `recall_sources` and `recall_ranks` so the source
routes and their ranks are traceable (required by S1 acceptance).

Route weights: popular is the strongest single route on validation P@10, but
with w=1.0 it monopolizes the fused list (every route's top-20 is disjoint,
so a 1.0-weighted route always wins ties of rank). We down-weight popular to
0.6 so cross-route consensus items can surface, and scale the remaining
routes by sqrt of their validation P@10 ratio (floor 0.2). k=20 sharpens
rank influence vs the canonical k=60.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from recommender.contracts import (
    Algorithm,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResult,
)

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ["popular", "content", "itemcf", "als", "cold_start"]

ROUTE_WEIGHTS = {
    "popular": 0.6,
    "cold_start": 0.63,
    "content": 0.52,
    "itemcf": 0.48,
    "als": 0.22,
}

DEFAULT_PARAMS = {"k": 20, "topn_per_route": 20, "routes": ROUTES, "weights": ROUTE_WEIGHTS}


def train(runtime_mode: str, out_dir: Path) -> None:
    """No model fitting needed; write the fusion parameter artifact."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "rrf_params.json", "w", encoding="utf-8") as f:
        json.dump(DEFAULT_PARAMS, f, indent=2, ensure_ascii=False)
    print(f"RRF params artifact saved to {out_dir / 'rrf_params.json'}")


class RRFProvider:
    algorithm = Algorithm.rrf_fusion
    model_version = "rrf-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        with open(self.model_manifest_path.parent / "rrf_params.json", encoding="utf-8") as f:
            params = json.load(f)
        self.k: int = params["k"]
        self.topn: int = params["topn_per_route"]
        self.weights: dict[str, float] = params["weights"]
        self.routes: list[str] = params["routes"]

        # Instantiate base providers pointing at manifests in the SAME mode directory.
        models_dir = self.model_manifest_path.parent.parent  # models/<mode>/
        from .popular import PopularProvider
        from .content import ContentProvider
        from .itemcf import ItemCFProvider
        from .als import ALSProvider
        from .cold_start import ColdStartProvider

        self.providers = {
            "popular": PopularProvider(models_dir / "popular-v1" / "manifest.json"),
            "content": ContentProvider(models_dir / "content-v1" / "manifest.json"),
            "itemcf": ItemCFProvider(models_dir / "itemcf-v1" / "manifest.json"),
            "als": ALSProvider(models_dir / "als-v1" / "manifest.json"),
            "cold_start": ColdStartProvider(models_dir / "cold-start-v1" / "manifest.json"),
        }

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        # Collect per-route candidate lists
        fused: dict[str, float] = {}
        sources: dict[str, list[str]] = {}
        ranks: dict[str, dict[str, int]] = {}

        for route in self.routes:
            provider = self.providers[route]
            sub_request = RecommendationRequest(
                request.subject_kind, request.subject_id, self.topn,
                request.runtime_mode, request.dataset_version, request.split_version,
            )
            try:
                sub_result = provider.recommend(sub_request)
            except Exception:
                continue  # a failing route is skipped, fusion stays available
            w = self.weights.get(route, 1.0)
            for item in sub_result.items:
                mid = item.movie_id
                fused[mid] = fused.get(mid, 0.0) + w / (self.k + item.rank)
                sources.setdefault(mid, []).append(route)
                ranks.setdefault(mid, {})[route] = item.rank

        ranked = sorted(fused.items(), key=lambda x: (-x[1], int(x[0])))[: request.limit]

        items = []
        for rank, (mid, score) in enumerate(ranked, 1):
            items.append(
                RecommendationItem(
                    movie_id=mid,
                    rank=rank,
                    algorithm=self.algorithm,
                    model_version=self.model_version,
                    score=round(score, 6),
                    recall_sources=sources[mid],
                    recall_ranks=ranks[mid],
                )
            )

        return RecommendationResult(
            status="ready",
            algorithm=self.algorithm,
            model_version=self.model_version,
            dataset_version=request.dataset_version,
            split_version=request.split_version,
            runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc),
            items=items,
        )
