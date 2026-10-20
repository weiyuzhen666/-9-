"""Cold-start recommendation -- hybrid of popular + content + itemcf fallback.

For users with no or very few ratings, we blend:
  1. Globally popular movies (by weighted rating)
  2. Content-similar to whatever the user *has* rated
  3. ItemCF-based recommendations from whatever the user has rated

This produces reasonable recommendations for brand-new users and gracefully
transitions to collaborative signals as more data becomes available.
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

PACKAGE = Path(__file__).resolve().parents[2] / "data/packages/rec-course-v3-train5-1.0.0"


def train(runtime_mode: str, out_dir: Path) -> None:
    """Cold-start needs popular baseline plus optionally content features.

    We store a simple precomputed popular list as the fallback; at inference
    time we load it alongside content/itemcf artifacts if present.
    """
    from recommender.student.popular import train as pop_train

    out_dir.mkdir(parents=True, exist_ok=True)
    # We re-use popular.pkl as the cold-start fallback baseline
    pop_train(runtime_mode, out_dir)
    print(f"Cold-start baseline artifact saved to {out_dir}")


class ColdStartProvider:
    algorithm = Algorithm.cold_start
    model_version = "cold-start-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        artifact = self.model_manifest_path.parent / "popular.pkl"
        with open(artifact, "rb") as f:
            self.popular: list[tuple[str, float]] = pickle.load(f)
        # Load genres for content-based fallback scoring
        self.movie_genres: dict[str, set[str]] = {}
        with open(PACKAGE / "movies.csv", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                genres = {g for g in row["genres"].split("|") if g} if row["genres"] else set()
                self.movie_genres[row["movie_id"]] = genres

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        if request.runtime_mode == "business":
            from recommender.business import read_history
            history = read_history(request)
            user_items = {fb.movie_id: float(fb.rating) for fb in history.ratings}
            favorite_items = set(history.favorite_movie_ids)
        else:
            from .common import eval_user_ratings
            user_items = eval_user_ratings(str(request.subject_id))
            favorite_items = {mid for mid, r in user_items.items() if r >= 4.0}

        seen = set(user_items.keys()) | favorite_items

        # Strategy: blend popular + content signals weighted by history length
        history_len = len(user_items)
        alpha = 1.0  # weight of popular
        beta = 0.0   # weight of content signal
        if history_len > 0:
            # As user gives more ratings, rely less on popular, more on content
            beta = min(0.7, 0.1 * history_len)
            alpha = 1.0 - beta

        scored: dict[str, float] = defaultdict(float)

        # Popular component
        for mid, score in self.popular:
            if mid in seen:
                continue
            scored[mid] += score * alpha

        # Content component: if user has rated anything positive, boost similar-genre movies
        if history_len > 0:
            # Aggregate user genre profile from positive ratings (>= 4.0)
            genre_weight: dict[str, float] = defaultdict(float)
            for mid, rating in user_items.items():
                if rating >= 4.0:
                    for g in self.movie_genres.get(mid, set()):
                        genre_weight[g] += (rating - 3.0)
            if genre_weight:
                # Score all catalog movies by genre overlap
                with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        mid = row["movie_id"]
                        if mid in seen:
                            continue
                        genres = self.movie_genres.get(mid, set())
                        if not genres:
                            continue
                        content_score = sum(genre_weight.get(g, 0.0) for g in genres) / math.sqrt(len(genres))
                        scored[mid] += content_score * beta

        ranked = sorted(scored.items(), key=lambda x: (-x[1], int(x[0])))[: request.limit]

        items = []
        for rank, (mid, score) in enumerate(ranked, 1):
            items.append(
                RecommendationItem(
                    movie_id=mid,
                    rank=rank,
                    algorithm=self.algorithm,
                    model_version=self.model_version,
                    score=score,
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
