"""Train all recommendation models and generate manifest.json for each.

Run this from the project root:
    python -m recommender.student.train_models

Generates artifacts under models/business/{algorithm}-v1/ and writes manifest.json
with correct sha256 for each artifact.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATASET_ROOT = PROJECT_ROOT / "data/packages/rec-course-v3-train5-1.0.0"
MODELS_ROOT = PROJECT_ROOT / "models/business"

# Fixed identities from recommender/data.py
DATASET = "rec-course-v3-train5-1.0.0"
SPLIT = "temporal-v1-cold500-train5-v3"
SCHEMA = "student-eight-v3"

MANIFEST_SHA_EXPECTED = "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest_identity() -> None:
    manifest_path = DATASET_ROOT / "manifest.json"
    actual = sha256_file(manifest_path)
    print(f"Dataset manifest sha256: {actual}")
    if actual != MANIFEST_SHA_EXPECTED:
        print(f"WARNING: manifest sha256 mismatch! Expected {MANIFEST_SHA_EXPECTED}")


def get_dataset_file_sha(name: str) -> str:
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return manifest["files"][name]["sha256"]


def build_manifest(
    algorithm: str,
    model_version: str,
    artifacts_dir: Path,
    artifact_names: list[str],
    parameters: dict,
    training_file: str = "business/history_ratings.csv",
) -> dict:
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]

    artifacts = {}
    for name in artifact_names:
        artifacts[name] = sha256_file(artifacts_dir / name)

    return {
        "algorithm": algorithm,
        "model_version": model_version,
        "runtime_mode": "business",
        "dataset_version": DATASET,
        "split_version": SPLIT,
        "schema_version": SCHEMA,
        "manifest_sha256": MANIFEST_SHA_EXPECTED,
        "training_files": {training_file: files[training_file]["sha256"]},
        "feature_files": {
            "movies.csv": files["movies.csv"]["sha256"],
            "training-catalog.csv": files["training-catalog.csv"]["sha256"],
        },
        "artifacts": artifacts,
        "parameters": parameters,
        "tool_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "pure_python": "1.0",
        },
    }


def train_all() -> None:
    check_manifest_identity()

    import recommender.student.popular as popular
    import recommender.student.content as content
    import recommender.student.itemcf as itemcf
    import recommender.student.als as als
    import recommender.student.cold_start as cold_start

    configs = [
        ("popular", "popular-v1", popular, {"m_threshold": 25}),
        ("content", "content-v1", content, {"topk_neighbors": 50, "idf": "standard"}),
        ("itemcf", "itemcf-v1", itemcf, {"topk_neighbors": 50, "centering": "item_mean"}),
        ("als", "als-v1", als, {"rank": 20, "iterations": 15, "reg": 0.1}),
        ("cold_start", "cold-start-v1", cold_start, {"blend_alpha_base": 1.0, "cold_start_strategy": "popular+content"}),
    ]

    for algorithm, version, mod, params in configs:
        out_dir = MODELS_ROOT / f"{algorithm}-v1"
        print(f"\n{'=' * 60}")
        print(f"Training {algorithm} -> {out_dir}")
        print("=" * 60)

        # Dispatch train call
        if hasattr(mod, "train"):
            if algorithm == "als":
                mod.train("business", out_dir, rank=20, iterations=15, reg=0.1)
            elif algorithm == "content":
                mod.train("business", out_dir, topk=50)
            elif algorithm == "itemcf":
                mod.train("business", out_dir, topk=50)
            else:
                mod.train("business", out_dir)
        else:
            print(f"  WARNING: {algorithm} has no train() function")
            continue

        # Find generated artifact files
        artifact_names = []
        for f in sorted(out_dir.iterdir()):
            if f.is_file() and f.suffix != ".json":
                artifact_names.append(f.name)

        # Write manifest.json
        manifest = build_manifest(
            algorithm=algorithm,
            model_version=version,
            artifacts_dir=out_dir,
            artifact_names=artifact_names,
            parameters=params,
        )
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Manifest written -> {manifest_path}")
        print(f"  Artifacts: {artifact_names}")

    print(f"\nAll models generated under {MODELS_ROOT}")


if __name__ == "__main__":
    train_all()
