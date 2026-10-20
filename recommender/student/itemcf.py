"""Item-based collaborative filtering -- optimized training.

Key optimization: only compute similarity for item pairs that share rated users,
avoiding the O(N^2) cartesian product over all 8459 catalog movies.
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


def train(runtime_mode: str, out_dir: Path, topk: int = 50, min_common: int = 3) -> None:
    """Build item-item similarities from training ratings efficiently.

    For each user with multiple ratings, generate candidate item pairs.
    Deduplicate and compute cosine over centered ratings.
    """
    training_file = "business/history_ratings.csv" if runtime_mode == "business" else "evaluation/train.csv"
    path = PACKAGE / training_file

    # Load catalog
    catalog = set()
    with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            catalog.add(row["movie_id"])

    # Build user-item ratings (sparse)
    user_items: dict[str, dict[str, float]] = defaultdict(dict)
    item_users: dict[str, dict[str, float]] = defaultdict(dict)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["userId"]
            mid = row["movieId"]
            if mid not in catalog:
                continue
            rating = float(row["rating"])
            user_items[uid][mid] = rating
            item_users[mid][uid] = rating

    print(f"Loaded {len(user_items)} users, {len(item_users)} items")

    # Compute item means for centering
    item_mean: dict[str, float] = {}
    for mid, users in item_users.items():
        item_mean[mid] = sum(users.values()) / len(users)

    # Generate candidate item pairs: for each user, pair all their rated items
    # This gives us only pairs that share at least one rater
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_dot: dict[tuple[str, str], float] = defaultdict(float)
    pair_norms: dict[str, float] = {}  # per-item norm of centered rating vector

    # First pass: compute centered vectors and norms per item
    item_vecs: dict[str, dict[str, float]] = {}
    for mid, users in item_users.items():
        mu = item_mean[mid]
        centered = {u: r - mu for u, r in users.items()}
        item_vecs[mid] = centered
        pair_norms[mid] = math.sqrt(sum(v * v for v in centered.values()))

    print("Computing candidate pairs from user co-rating...")

    # Second pass: for each user, accumulate pair dot products where they co-rate
    for uid, items in user_items.items():
        item_list = list(items.keys())
        if len(item_list) < 2:
            continue
        # Sort by movie_id to canonicalize pair order
        item_list.sort(key=lambda x: int(x))
        centered_for_user = {mid: items[mid] - item_mean[mid] for mid in item_list}
        for i in range(len(item_list)):
            for j in range(i + 1, len(item_list)):
                a, b = item_list[i], item_list[j]
                key = (a, b)
                pair_counts[key] += 1
                pair_dot[key] += centered_for_user[a] * centered_for_user[b]

    print(f"Generated {len(pair_counts)} candidate pairs")

    # Compute similarities
    print("Computing cosine similarities...")
    raw_sim: dict[tuple[str, str], float] = {}
    for (a, b), count in pair_counts.items():
        if count < min_common:
            continue
        na = pair_norms[a]
        nb = pair_norms[b]
        if na == 0 or nb == 0:
            continue
        sim = pair_dot[(a, b)] / (na * nb)
        if sim > 0:
            raw_sim[(a, b)] = sim

    print(f"Got {len(raw_sim)} valid positive similarities")

    # Build per-item top-K neighbors
    neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (a, b), sim in raw_sim.items():
        neighbors[a].append((b, sim))
        neighbors[b].append((a, sim))

    for mid in neighbors:
        neighbors[mid].sort(key=lambda x: (-x[1], int(x[0])))
        neighbors[mid] = neighbors[mid][:topk]

    print(f"ItemCF training complete. Saving artifact...")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "itemcf.pkl", "wb") as f:
        pickle.dump({"neighbors": dict(neighbors), "item_mean": item_mean}, f)
    print(f"Artifact saved to {out_dir / 'itemcf.pkl'}")


class ItemCFProvider:
    algorithm = Algorithm.itemcf
    model_version = "itemcf-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        artifact = self.model_manifest_path.parent / "itemcf.pkl"
        with open(artifact, "rb") as f:
            data = pickle.load(f)
        self.neighbors: dict[str, list[tuple[str, float]]] = data["neighbors"]
        self.item_mean: dict[str, float] = data["item_mean"]

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        if request.runtime_mode == "business":
            from recommender.business import read_history
            history = read_history(request)
            user_items = {fb.movie_id: float(fb.rating) for fb in history.ratings}
        else:
            user_items = {}

        scored: dict[str, float] = {}
        sim_sum: dict[str, float] = {}

        if not user_items:
            # Cold: fall back to popular by support count
            catalog_support = []
            with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    catalog_support.append((row["movie_id"], float(row["train_support"])))
            catalog_support.sort(key=lambda x: (-x[1], int(x[0])))
            for mid, sup in catalog_support[:request.limit]:
                scored[mid] = sup
        else:
            for mid, rating in user_items.items():
                if mid not in self.neighbors:
                    continue
                centered = rating - self.item_mean.get(mid, 3.5)
                for nb_mid, sim in self.neighbors[mid]:
                    if nb_mid in user_items:
                        continue
                    scored[nb_mid] = scored.get(nb_mid, 0.0) + sim * centered
                    sim_sum[nb_mid] = sim_sum.get(nb_mid, 0.0) + abs(sim)

            # Normalize
            for mid in scored:
                if sim_sum[mid] > 0:
                    scored[mid] = scored[mid] / sim_sum[mid] + self.item_mean.get(mid, 3.5)

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
