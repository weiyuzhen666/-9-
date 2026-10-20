"""ALS (Alternating Least Squares) matrix factorization -- lightweight version.

Uses a very small latent rank (k=8) and few iterations (5) to stay fast in
pure Python. Quality is not SOTA but sufficient to satisfy the contract
and provide actual collaborative filtering predictions.
"""
import csv
import math
import pickle
import random
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


def _solve_normal(A, b, reg_lambda, k):
    """Solve (A^T A + lambda I) x = A^T b. A is list of rows (list of floats)."""
    n = len(A)
    if n == 0:
        return [0.0] * k
    # A^T A (k x k)
    AtA = [[0.0] * k for _ in range(k)]
    for i in range(k):
        rowi = [A[r][i] for r in range(n)]
        for j in range(i, k):
            s = 0.0
            for row in rowi:
                s += row * A[rowi.index(row)][j] if False else 0.0
            # simpler
            s = 0.0
            for r in range(n):
                s += A[r][i] * A[r][j]
            AtA[i][j] = s
            AtA[j][i] = s
        AtA[i][i] += reg_lambda
    # A^T b (k-vector)
    Atb = [0.0] * k
    for i in range(k):
        Atb[i] = sum(A[r][i] * b[r] for r in range(n))
    # Solve via Gaussian elimination
    return _gauss(AtA, Atb, k)


def _gauss(A, b, n):
    """Gaussian elimination with partial pivoting."""
    aug = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        max_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[max_row] = aug[max_row], aug[col]
        pivot = aug[col][col]
        if abs(pivot) < 1e-10:
            continue
        inv = 1.0 / pivot
        for j in range(col, n + 1):
            aug[col][j] *= inv
        for r in range(n):
            if r == col:
                continue
            f = aug[r][col]
            for j in range(col, n + 1):
                aug[r][j] -= f * aug[col][j]
    return [aug[i][n] for i in range(n)]


def train(
    runtime_mode: str,
    out_dir: Path,
    rank: int = 8,
    iterations: int = 5,
    reg: float = 0.1,
    seed: int = 42,
) -> None:
    random.seed(seed)

    training_file = "business/history_ratings.csv" if runtime_mode == "business" else "evaluation/train.csv"
    path = PACKAGE / training_file

    catalog = set()
    with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            catalog.add(row["movie_id"])

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

    users = sorted(user_items.keys(), key=lambda x: int(x))
    items = sorted(item_users.keys(), key=lambda x: int(x))
    u_idx = {u: i for i, u in enumerate(users)}
    i_idx = {m: i for i, m in enumerate(items)}
    n_u, n_i = len(users), len(items)

    print(f"ALS: {n_u} users x {n_i} items, rank={rank}, iters={iterations}, reg={reg}")

    # Initialize factors
    U = [[random.uniform(-0.1, 0.1) for _ in range(rank)] for _ in range(n_u)]
    V = [[random.uniform(-0.1, 0.1) for _ in range(rank)] for _ in range(n_i)]

    for it in range(iterations):
        # Update U
        for u in range(n_u):
            uid = users[u]
            rated = user_items[uid]
            if not rated:
                continue
            A = [V[i_idx[mid]] for mid in rated]
            b = list(rated.values())
            U[u] = _solve_normal(A, b, reg, rank)

        # Update V
        for i in range(n_i):
            mid = items[i]
            raters = item_users[mid]
            if not raters:
                continue
            A = [U[u_idx[uid]] for uid in raters]
            b = list(raters.values())
            V[i] = _solve_normal(A, b, reg, rank)

        # RMSE
        se = 0.0
        n = 0
        for uid, rated in user_items.items():
            u = u_idx[uid]
            u_vec = U[u]
            for mid, r in rated.items():
                i = i_idx[mid]
                v_vec = V[i]
                pred = sum(a * b for a, b in zip(u_vec, v_vec))
                se += (pred - r) ** 2
                n += 1
        rmse = math.sqrt(se / n) if n else float("inf")
        print(f"  iter {it + 1}/{iterations} RMSE={rmse:.4f}")

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "als.pkl", "wb") as f:
        pickle.dump(
            {"U": U, "V": V, "users": users, "items": items, "u_idx": u_idx, "i_idx": i_idx, "rank": rank},
            f,
        )
    print(f"ALS done. Saved to {out_dir}")


class ALSProvider:
    algorithm = Algorithm.als
    model_version = "als-v1"
    model_manifest_path: str | Path

    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)
        artifact = self.model_manifest_path.parent / "als.pkl"
        with open(artifact, "rb") as f:
            data = pickle.load(f)
        self.U = data["U"]
        self.V = data["V"]
        self.users = data["users"]
        self.items = data["items"]
        self.u_idx = data["u_idx"]
        self.i_idx = data["i_idx"]

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        if request.runtime_mode == "business":
            from recommender.business import read_history
            history = read_history(request)
            user_items = {fb.movie_id: float(fb.rating) for fb in history.ratings}
        else:
            user_items = {}

        uid = str(request.subject_id)
        scored: list[tuple[str, float]] = []

        if uid in self.u_idx:
            u_vec = self.U[self.u_idx[uid]]
            seen = set(user_items.keys()) if user_items else set()
            for i, mid in enumerate(self.items):
                if mid in seen:
                    continue
                score = sum(a * b for a, b in zip(u_vec, self.V[i]))
                scored.append((mid, score))
        else:
            # Unknown user: popular fallback
            with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
                scored = [(row["movie_id"], float(row["train_support"])) for row in csv.DictReader(f)]

        scored.sort(key=lambda x: (-x[1], int(x[0])))
        top = scored[: request.limit]

        items = [
            RecommendationItem(
                movie_id=mid,
                rank=rank,
                algorithm=self.algorithm,
                model_version=self.model_version,
                score=score,
            )
            for rank, (mid, score) in enumerate(top, 1)
        ]

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
