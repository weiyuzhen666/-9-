"""Train remaining models individually so we can diagnose which fails."""
import sys
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

MODELS = ROOT / "models/business"
DATASET_ROOT = ROOT / "data/packages/rec-course-v3-train5-1.0.0"

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


def write_manifest(algorithm: str, version: str, artifact_names: list[str], params: dict):
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    out_dir = MODELS / f"{version}"
    artifacts = {n: sha256_file(out_dir / n) for n in artifact_names}
    manifest_dict = {
        "algorithm": algorithm,
        "model_version": version,
        "runtime_mode": "business",
        "dataset_version": DATASET,
        "split_version": SPLIT,
        "schema_version": SCHEMA,
        "manifest_sha256": MANIFEST_SHA_EXPECTED,
        "training_files": {"business/history_ratings.csv": files["business/history_ratings.csv"]["sha256"]},
        "feature_files": {
            "movies.csv": files["movies.csv"]["sha256"],
            "training-catalog.csv": files["training-catalog.csv"]["sha256"],
        },
        "artifacts": artifacts,
        "parameters": params,
        "tool_versions": {"python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "pure_python": "1.0"},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  manifest written: {out_dir / 'manifest.json'}")


def run_itemcf():
    print("=== ItemCF ===")
    from recommender.student import itemcf
    out = MODELS / "itemcf-v1"
    itemcf.train("business", out, topk=50, min_common=3)
    write_manifest("itemcf", "itemcf-v1", ["itemcf.pkl"], {"topk_neighbors": 50, "min_common": 3, "centering": "item_mean"})
    print("ItemCF OK\n")


def run_als():
    print("=== ALS ===")
    from recommender.student import als
    out = MODELS / "als-v1"
    als.train("business", out, rank=8, iterations=5, reg=0.1)
    write_manifest("als", "als-v1", ["als.pkl"], {"rank": 8, "iterations": 5, "reg": 0.1})
    print("ALS OK\n")


def run_cold_start():
    print("=== Cold Start ===")
    from recommender.student import cold_start
    out = MODELS / "cold-start-v1"
    cold_start.train("business", out)
    write_manifest("cold_start", "cold-start-v1", ["popular.pkl"], {"strategy": "popular_plus_content_blend"})
    print("Cold Start OK\n")


if __name__ == "__main__":
    # Run in sequence so output interleaving is clear
    run_itemcf()
    run_als()
    run_cold_start()
    print("ALL DONE")
