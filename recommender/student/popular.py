"""Popular recommendation -- rank movies by weighted rating.

Offline training writes popular.pkl (sorted list of movie_ids with score).
Provider loads the artifact and returns top-N, excluding already-seen items.
"""
import csv
import math
import pickle
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from recommender.contracts import (
    Algorithm,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResult,
)
from recommender.data import DATASET, SPLIT, ContractError, require


PACKAGE = Path(__file__).resolve().parents[2] / "data/packages/rec-course-v3-train5-1.0.0"


def train(runtime_mode: str, out_dir: Path) -> list[tuple[str, float]]:
    """Compute globally popular movies using IMDB-style weighted rating."""
    training_file = "business/history_ratings.csv" if runtime_mode == "business" else "evaluation/train.csv"
    path = PACKAGE / training_file
    movie_ratings: dict[str, list[float]] = defaultdict(list)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            movie_ratings[row["movieId"]].append(float(row["rating"]))
    catalog = set()
    with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            catalog.add(row["movie_id"])
    # Weighted rating (m = 25 quantile of vote count, C = mean rating)
    counts = [len(v) for v in movie_ratings.values()]
    counts.sort()
    m = counts[len(counts) // 4] if counts else 25
    all_ratings = [r for rs in movie_ratings.values() for r in rs]
    C = sum(all_ratings) / len(all_ratings) if all_ratings else 3.0
    scored: list[tuple[str, float]] = []
    for mid, rs in movie_ratings.items():
        if mid not in catalog:
            continue
        v = len(rs)
        R = sum(rs) / v
        score = (v / (v + m)) * R + (m / (v + m)) * C
        scored.append((mid, score))
    scored.sort(key=lambda x: (-x[1], int(x[0])))
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "popular.pkl", "wb") as f:
        pickle.dump(scored, f)
    return scored


class PopularProvider:
    algorithm = Algorithm.popular
    model_version = "popular-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        artifact = self.model_manifest_path.parent / "popular.pkl"
        with open(artifact, "rb") as f:
            self.items: list[tuple[str, float]] = pickle.load(f)

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        if request.runtime_mode == "business":
            from recommender.business import read_history
            history = read_history(request)
            seen = {fb.movie_id for fb in history.ratings} | set(history.favorite_movie_ids)
        else:
            seen = set()

        results: list[RecommendationItem] = []
        rank = 1
        for mid, score in self.items:
            if rank > request.limit:
                break
            if mid in seen:
                continue
            results.append(
                RecommendationItem(
                    movie_id=mid,
                    rank=rank,
                    algorithm=self.algorithm,
                    model_version=self.model_version,
                    score=score,
                )
            )
            rank += 1

        return RecommendationResult(
            status="ready",
            algorithm=self.algorithm,
            model_version=self.model_version,
            dataset_version=request.dataset_version,
            split_version=request.split_version,
            runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc),
            items=results,
        )
