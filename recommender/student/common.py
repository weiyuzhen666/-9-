"""Shared utilities for student recommendation algorithms."""
import csv
import hashlib
import json
import math
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Absolute package root -- works both inside Docker and locally.
PACKAGE = Path(__file__).resolve().parents[2] / "data/packages/rec-course-v3-train5-1.0.0"


def now_utc_iso() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))


def load_movies() -> dict[str, dict]:
    """movie_id -> {genres: set[str], title: str, ...}"""
    movies = {}
    path = PACKAGE / "movies.csv"
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            mid = row["movie_id"]
            genres = {g for g in row["genres"].split("|") if g} if row["genres"] else set()
            movies[mid] = {"genres": genres, "title": row["movielens_title"]}
    return movies


def load_catalog() -> set[str]:
    path = PACKAGE / "training-catalog.csv"
    ids = set()
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ids.add(row["movie_id"])
    return ids


def load_training_ratings() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Returns (user->item->rating, item->user->rating) using the business ratings file."""
    user_items: dict[str, dict[str, float]] = defaultdict(dict)
    item_users: dict[str, dict[str, float]] = defaultdict(dict)
    path = PACKAGE / "business/history_ratings.csv"
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["userId"]
            mid = row["movieId"]
            rating = float(row["rating"])
            user_items[uid][mid] = rating
            item_users[mid][uid] = rating
    return user_items, item_users


def load_eval_ratings() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Returns (user->item->rating, item->user->rating) from evaluation/train.csv."""
    user_items: dict[str, dict[str, float]] = defaultdict(dict)
    item_users: dict[str, dict[str, float]] = defaultdict(dict)
    path = PACKAGE / "evaluation/train.csv"
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["userId"]
            mid = row["movieId"]
            rating = float(row["rating"])
            user_items[uid][mid] = rating
            item_users[mid][uid] = rating
    return user_items, item_users


_EVAL_TRAIN_CACHE: dict[str, dict[str, float]] | None = None


def eval_user_ratings(uid: str) -> dict[str, float]:
    """User's ratings from evaluation/train.csv (cached). Used by providers in evaluation mode."""
    global _EVAL_TRAIN_CACHE
    if _EVAL_TRAIN_CACHE is None:
        user_items, _ = load_eval_ratings()
        _EVAL_TRAIN_CACHE = user_items
    return _EVAL_TRAIN_CACHE.get(uid, {})


def cosine(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity of two sparse vectors."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    na = math.sqrt(sum(v * v for v in vec_a.values()))
    nb = math.sqrt(sum(v * v for v in vec_b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def euclidean(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dist = math.sqrt(sum((vec_a[k] - vec_b[k]) ** 2 for k in common))
    return 1.0 / (1.0 + dist)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_model_manifest(
    algorithm: str,
    model_version: str,
    runtime_mode: str,
    artifacts_dir: Path,
    artifacts: dict[str, str],
    training_file: str,
    tool_versions: dict[str, str],
    feature_files: dict[str, str] | None = None,
    parameters: dict | None = None,
) -> dict:
    manifest = load_manifest()
    files = manifest["files"]
    return {
        "algorithm": algorithm,
        "model_version": model_version,
        "runtime_mode": runtime_mode,
        "dataset_version": manifest["dataset_version"],
        "split_version": manifest["split_version"],
        "schema_version": manifest["schema_version"],
        "manifest_sha256": sha256_file(Path(__file__).resolve().parents[2] / "data/packages/rec-course-v3-train5-1.0.0/manifest.json"),
        "training_files": {training_file: files[training_file]["sha256"]},
        "feature_files": feature_files or {},
        "artifacts": artifacts,
        "parameters": parameters or {},
        "tool_versions": tool_versions,
    }
