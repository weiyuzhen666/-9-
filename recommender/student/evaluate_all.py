"""Offline evaluation pipeline: retrain on evaluation/train.csv, compute Precision@10 / Recall@10."""
import csv
import json
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"d:\tuijianxitong\CineLab-Student-Windows-1.3.0-rc1")
sys.path.insert(0, str(ROOT))

PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUT_DIR = ROOT / "models/evaluation"
POSITIVE_THRESHOLD = 4.0
TOP_K = 10


def load_eligible_users(partition: str) -> set[str]:
    if partition in ("validation", "test"):
        path = PACKAGE / "evaluation/evaluation-eligibility.csv"
        ids = set()
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["partition"] == partition and row["eligible"] == "1":
                    ids.add(row["userId"])
    else:
        path = PACKAGE / f"evaluation/{partition}-users.csv"
        ids = set()
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["eligible"] == "1":
                    ids.add(row["userId"])
    print(f"  Eligible users ({partition}): {len(ids)}")
    return ids


def load_train_ratings() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    user_items: dict[str, dict[str, float]] = defaultdict(dict)
    item_users: dict[str, dict[str, float]] = defaultdict(dict)
    with open(PACKAGE / "evaluation/train.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            uid, mid, rating = row["userId"], row["movieId"], float(row["rating"])
            user_items[uid][mid] = rating
            item_users[mid][uid] = rating
    print(f"  Train: {len(user_items)} users, {len(item_users)} items, "
          f"{sum(len(v) for v in user_items.values())} ratings")
    return user_items, item_users


def load_eval_ground_truth(partition: str) -> dict[str, set[str]]:
    """uid -> set of positive movie_ids (rating >= 4.0 in this partition)."""
    path = PACKAGE / f"evaluation/{partition}.csv"
    positives: dict[str, set[str]] = defaultdict(set)
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            uid, mid, rating = row["userId"], row["movieId"], float(row["rating"])
            if rating >= POSITIVE_THRESHOLD:
                positives[uid].add(mid)
    count = sum(len(v) for v in positives.values())
    print(f"  GT ({partition}): {len(positives)} users with positives, {count} total positives")
    return positives


def load_exclusions(partition: str) -> dict[str, set[str]]:
    """uid -> excluded movie_ids (train + validation for test partition)."""
    exclusions: dict[str, set[str]] = defaultdict(set)
    sources = ["evaluation/train.csv"]
    if partition == "test":
        sources.append("evaluation/validation.csv")
    for src in sources:
        with open(PACKAGE / src, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                exclusions[row["userId"]].add(row["movieId"])
    return exclusions


def load_catalog() -> set[str]:
    ids = set()
    with open(PACKAGE / "training-catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ids.add(row["movie_id"])
    print(f"  Catalog: {len(ids)} movies")
    return ids


def load_movies() -> dict[str, dict]:
    movies = {}
    with open(PACKAGE / "movies.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mid = row["movie_id"]
            genres = {g for g in row["genres"].split("|") if g} if row["genres"] else set()
            movies[mid] = {"genres": genres, "title": row["movielens_title"]}
    return movies


# ===================== Retrain algorithms on evaluation/train.csv =====================

def retrain_all():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = {}

    print("\n=== Retraining on evaluation/train.csv ===")
    from recommender.student import popular, content, itemcf, als, cold_start
    from recommender.student.common import build_model_manifest, sha256_file

    # Popular
    print("1. Popular...")
    popular.train("evaluation", OUT_DIR / "popular-v1")
    artifacts["popular"] = OUT_DIR / "popular-v1" / "popular.pkl"

    # Content
    print("2. Content...")
    content.train("evaluation", OUT_DIR / "content-v1")
    artifacts["content"] = OUT_DIR / "content-v1" / "content.pkl"

    # ItemCF
    print("3. ItemCF...")
    itemcf.train("evaluation", OUT_DIR / "itemcf-v1", topk=50, min_common=3)
    artifacts["itemcf"] = OUT_DIR / "itemcf-v1" / "itemcf.pkl"

    # ALS
    print("4. ALS...")
    als.train("evaluation", OUT_DIR / "als-v1", rank=8, iterations=5, reg=0.1)
    artifacts["als"] = OUT_DIR / "als-v1" / "als.pkl"

    # Cold Start
    print("5. Cold Start...")
    cold_start.train("evaluation", OUT_DIR / "cold-start-v1")
    artifacts["cold_start"] = OUT_DIR / "cold-start-v1" / "popular.pkl"

    print("All retrained.\n")


# ===================== Offline recommenders (evaluation mode) =====================

def recommend_popular(top_n: int, exclude: set[str], catalog: set[str]) -> list[str]:
    popular_path = OUT_DIR / "popular-v1" / "popular.pkl"
    with open(popular_path, "rb") as f:
        scored = pickle.load(f)
    return [mid for mid, _ in scored if mid in catalog and mid not in exclude][:top_n]


def recommend_content(user_train: dict[str, float], top_n: int, exclude: set[str],
                       catalog: set[str], movies: dict[str, dict]) -> list[str]:
    """Content-based: build user genre profile from positive train ratings, rank by genre overlap."""
    # User profile: weighted genre counts from positive train ratings (>= 4.0)
    profile: dict[str, float] = defaultdict(float)
    for mid, rating in user_train.items():
        if mid not in movies:
            continue
        for g in movies[mid]["genres"]:
            profile[g] += rating - 3.0  # center around 3.0

    if not profile:
        return recommend_popular(top_n, exclude, catalog)

    # Score all catalog movies
    scored: list[tuple[str, float]] = []
    for mid in catalog:
        if mid in exclude or mid not in movies:
            continue
        genres = movies[mid]["genres"]
        if not genres:
            continue
        score = sum(profile.get(g, 0.0) for g in genres)
        scored.append((mid, score))
    scored.sort(key=lambda x: (-x[1], int(x[0])))
    return [mid for mid, _ in scored[:top_n]]


def recommend_itemcf(user_train: dict[str, float], top_n: int, exclude: set[str],
                      catalog: set[str]) -> list[str]:
    itemcf_path = OUT_DIR / "itemcf-v1" / "itemcf.pkl"
    with open(itemcf_path, "rb") as f:
        data = pickle.load(f)
    neighbors = data["neighbors"]
    item_mean = data["item_mean"]

    if not user_train:
        return recommend_popular(top_n, exclude, catalog)

    scored: dict[str, float] = {}
    sim_sum: dict[str, float] = {}
    for mid, rating in user_train.items():
        if mid not in neighbors:
            continue
        centered = rating - item_mean.get(mid, 3.5)
        for nb_mid, sim in neighbors[mid]:
            if nb_mid in user_train or nb_mid not in catalog or nb_mid in exclude:
                continue
            scored[nb_mid] = scored.get(nb_mid, 0.0) + sim * centered
            sim_sum[nb_mid] = sim_sum.get(nb_mid, 0.0) + abs(sim)

    for mid in scored:
        if sim_sum[mid] > 0:
            scored[mid] = scored[mid] / sim_sum[mid] + item_mean.get(mid, 3.5)

    ranked = sorted(scored.items(), key=lambda x: (-x[1], int(x[0])))
    return [mid for mid, _ in ranked[:top_n]]


def recommend_als(user_train: dict[str, float], top_n: int, exclude: set[str],
                   catalog: set[str]) -> list[str]:
    """ALS with pure Python SGD factorization. For known users we use the learned U vector.
    For unknown users or users not in training we estimate U from their train ratings."""
    als_path = OUT_DIR / "als-v1" / "als.pkl"
    with open(als_path, "rb") as f:
        data = pickle.load(f)
    V = data["V"]           # item vectors (list of lists)
    items = data["items"]   # item IDs in order
    u_idx = data["u_idx"]   # uid -> index
    rank = data["rank"]
    item_vec = {mid: V[i] for i, mid in enumerate(items)}

    if not user_train:
        return recommend_popular(top_n, exclude, catalog)

    # Estimate user vector from train ratings: solve for u given known v_i for each rated item
    # u = (sum_i r_i * v_i) / (sum_i ||v_i||^2)  -- simple projection
    numerator = [0.0] * rank
    denominator = [0.0] * rank
    rated_with_vec = 0
    for mid, rating in user_train.items():
        if mid not in item_vec:
            continue
        v = item_vec[mid]
        for d in range(rank):
            numerator[d] += rating * v[d]
            denominator[d] += v[d] * v[d]
        rated_with_vec += 1

    if rated_with_vec == 0:
        return recommend_popular(top_n, exclude, catalog)

    u_vec = [numerator[d] / denominator[d] if denominator[d] > 0 else 0.0 for d in range(rank)]

    scored: list[tuple[str, float]] = []
    for mid in catalog:
        if mid in exclude or mid not in item_vec:
            continue
        pred = sum(u_vec[d] * item_vec[mid][d] for d in range(rank))
        scored.append((mid, pred))
    scored.sort(key=lambda x: (-x[1], int(x[0])))
    return [mid for mid, _ in scored[:top_n]]


def recommend_cold_start(user_train: dict[str, float], top_n: int, exclude: set[str],
                          catalog: set[str], movies: dict[str, dict]) -> list[str]:
    """Cold start: popular if no user data, else blend popular + content."""
    if len(user_train) == 0:
        return recommend_popular(top_n, exclude, catalog)

    # Blend: 60% content signal, 40% popular signal
    content_ids = set(recommend_content(user_train, top_n * 3, exclude, catalog, movies))
    popular_ids = set(recommend_popular(top_n * 3, exclude, catalog))
    blended = list(content_ids & popular_ids) + list(content_ids - popular_ids) + list(popular_ids - content_ids)
    return blended[:top_n]


# ===================== Precision / Recall =====================

def compute_metrics(recommended: list[str], ground_truth: set[str]) -> tuple[float, float]:
    if not recommended:
        return 0.0, 0.0
    hits = len(set(recommended) & ground_truth)
    precision = hits / len(recommended)
    recall = hits / max(len(ground_truth), 1)
    return precision, recall


# ===================== Main evaluation loop =====================

def run_evaluation():
    print("=" * 60)
    print("OFFLINE EVALUATION: Precision@10 / Recall@10")
    print("=" * 60)

    # Load shared data
    catalog = load_catalog()
    movies = load_movies()
    user_items, item_users = load_train_ratings()

    partitions = ["validation", "test"]
    all_results = {}

    for partition in partitions:
        print(f"\n{'='*40}")
        print(f"Partition: {partition}")
        print(f"{'='*40}")

        eligible = load_eligible_users(partition)
        gt = load_eval_ground_truth(partition)
        exclusions = load_exclusions(partition)

        results = {algo: {"precisions": [], "recalls": [], "count": 0, "empty": 0}
                   for algo in ["popular", "content", "itemcf", "als", "cold_start"]}

        for uid in sorted(eligible, key=int):
            train = user_items.get(uid, {})
            gt_set = gt.get(uid, set())
            exclude = exclusions.get(uid, set())

            # Each recommender
            rec_pop = recommend_popular(TOP_K, exclude, catalog)
            rec_cont = recommend_content(train, TOP_K, exclude, catalog, movies)
            rec_icf = recommend_itemcf(train, TOP_K, exclude, catalog)
            rec_als = recommend_als(train, TOP_K, exclude, catalog)
            rec_cs = recommend_cold_start(train, TOP_K, exclude, catalog, movies)

            for algo_name, rec_ids in [("popular", rec_pop), ("content", rec_cont),
                                        ("itemcf", rec_icf), ("als", rec_als), ("cold_start", rec_cs)]:
                p, r = compute_metrics(rec_ids, gt_set)
                results[algo_name]["precisions"].append(p)
                results[algo_name]["recalls"].append(r)
                results[algo_name]["count"] += 1
                if not rec_ids:
                    results[algo_name]["empty"] += 1

        # Macro average
        all_results[partition] = {}
        print(f"\n  {'Algorithm':<15} {'Users':>6} {'Prec@10':>9} {'Rec@10':>8}")
        print(f"  {'-'*50}")
        for algo_name in ["popular", "content", "itemcf", "als", "cold_start"]:
            res = results[algo_name]
            n = res["count"]
            avg_p = sum(res["precisions"]) / n if n else 0.0
            avg_r = sum(res["recalls"]) / n if n else 0.0
            all_results[partition][algo_name] = {
                "user_count": n, "avg_precision_at_10": round(avg_p, 5),
                "avg_recall_at_10": round(avg_r, 5), "empty_results": res["empty"],
            }
            print(f"  {algo_name:<15} {n:>6} {avg_p:>9.5f} {avg_r:>8.5f}")

    # Save results
    out_path = ROOT / "models/evaluation/metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nMetrics saved to: {out_path}")

    print("\n=== Summary ===")
    for partition in partitions:
        print(f"\n  [{partition}]")
        sorted_algos = sorted(all_results[partition].items(),
                              key=lambda x: -x[1]["avg_precision_at_10"])
        for algo, vals in sorted_algos:
            print(f"    {algo:<12} P@10={vals['avg_precision_at_10']:.4f}  "
                  f"R@10={vals['avg_recall_at_10']:.4f}  (n={vals['user_count']})")


if __name__ == "__main__":
    retrain_all()
    run_evaluation()
