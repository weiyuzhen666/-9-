"""Content-based recommendation using movie genre TF-IDF and Jaccard similarity.

Offline training writes content.pkl (genres vectors + precomputed top-K neighbours per movie).
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


def train(runtime_mode: str, out_dir: Path, topk: int = 50) -> None:
    """Build genre similarity matrix and precompute top neighbours per movie."""
    # Load catalog
    catalog = set()
    with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            catalog.add(row["movie_id"])

    # Load movies and build genre vectors
    movie_genres: dict[str, set[str]] = {}
    genre_movies: dict[str, set[str]] = defaultdict(set)
    with open(PACKAGE / "movies.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mid = row["movie_id"]
            if mid not in catalog:
                continue
            genres = {g for g in row["genres"].split("|") if g} if row["genres"] else set()
            movie_genres[mid] = genres
            for g in genres:
                genre_movies[g].add(mid)

    # IDF for genres
    N = len(movie_genres)
    idf: dict[str, float] = {}
    for g, movies in genre_movies.items():
        idf[g] = math.log((1 + N) / (1 + len(movies))) + 1.0

    # Build TF-IDF vectors per movie
    vectors: dict[str, dict[str, float]] = {}
    for mid, genres in movie_genres.items():
        tfidf = {}
        for g in genres:
            tfidf[g] = idf[g]
        vectors[mid] = tfidf

    # Precompute top-K neighbours per movie using cosine similarity on genre vectors
    all_mids = list(movie_genres.keys())
    neighbors: dict[str, list[tuple[str, float]]] = {}
    for mid in all_mids:
        v_a = vectors[mid]
        scored = []
        for other in all_mids:
            if other == mid:
                continue
            v_b = vectors[other]
            common = set(v_a) & set(v_b)
            if not common:
                continue
            dot = sum(v_a[k] * v_b[k] for k in common)
            na = math.sqrt(sum(v * v for v in v_a.values()))
            nb = math.sqrt(sum(v * v for v in v_b.values()))
            sim = dot / (na * nb) if na > 0 and nb > 0 else 0.0
            if sim > 0:
                scored.append((other, sim))
        scored.sort(key=lambda x: (-x[1], int(x[0])))
        neighbors[mid] = scored[:topk]

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "content.pkl", "wb") as f:
        pickle.dump({"vectors": vectors, "neighbors": neighbors, "movie_genres": movie_genres}, f)


class ContentProvider:
    algorithm = Algorithm.content
    model_version = "content-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        artifact = self.model_manifest_path.parent / "content.pkl"
        with open(artifact, "rb") as f:
            data = pickle.load(f)
        self.vectors: dict[str, dict[str, float]] = data["vectors"]
        self.neighbors: dict[str, list[tuple[str, float]]] = data["neighbors"]
        self.movie_genres: dict[str, set[str]] = data["movie_genres"]

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        if request.runtime_mode == "business":
            from recommender.business import read_history
            history = read_history(request)
            user_items = {fb.movie_id: float(fb.rating) for fb in history.ratings}
        else:
            from .common import eval_user_ratings
            user_items = eval_user_ratings(str(request.subject_id))

        scored: dict[str, float] = {}
        if not user_items:
            # No history: fall back to popular by train_support
            catalog_support = []
            with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    catalog_support.append((row["movie_id"], float(row["train_support"])))
            catalog_support.sort(key=lambda x: (-x[1], int(x[0])))
            for mid, sup in catalog_support[:request.limit]:
                scored[mid] = sup
        else:
            # Aggregate similarities from all user items, weighted by rating
            for mid, rating in user_items.items():
                if mid not in self.neighbors:
                    continue
                weight = max(0.1, (rating - 2.5) / 2.5)  # normalize around 0
                for nb_mid, sim in self.neighbors[mid]:
                    if nb_mid in user_items:
                        continue
                    scored[nb_mid] = scored.get(nb_mid, 0.0) + sim * weight

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
