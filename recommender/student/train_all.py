"""Train all remaining models + write manifests."""
import sys, json, hashlib
from pathlib import Path

ROOT = Path(r"d:\tuijianxitong\CineLab-Student-Windows-1.3.0-rc1")
sys.path.insert(0, str(ROOT))

MODELS = ROOT / "models/business"
DATASET_ROOT = ROOT / "data/packages/rec-course-v3-train5-1.0.0"

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def write_manifest(algo, version, art_names, params):
    data_manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    files = data_manifest["files"]
    out = MODELS / version
    arts = {n: sha256(out / n) for n in art_names}
    m = {
        "algorithm": algo,
        "model_version": version,
        "runtime_mode": "business",
        "dataset_version": "rec-course-v3-train5-1.0.0",
        "split_version": "temporal-v1-cold500-train5-v3",
        "schema_version": "student-eight-v3",
        "manifest_sha256": "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e",
        "training_files": {"business/history_ratings.csv": files["business/history_ratings.csv"]["sha256"]},
        "feature_files": {
            "movies.csv": files["movies.csv"]["sha256"],
            "training-catalog.csv": files["training-catalog.csv"]["sha256"],
        },
        "artifacts": arts,
        "parameters": params,
        "tool_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "pure_python": "1.0",
        },
    }
    target = out / "manifest.json"
    target.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  manifest written -> {target}")

# ----- ItemCF -----
print("=== ItemCF ===")
from recommender.student import itemcf
itemcf.train("business", MODELS / "itemcf-v1", topk=50, min_common=3)
write_manifest("itemcf", "itemcf-v1", ["itemcf.pkl"], {"topk": 50, "min_common": 3, "centering": "item_mean"})
print("ItemCF OK\n")

# ----- ALS -----
print("=== ALS ===")
from recommender.student import als
als.train("business", MODELS / "als-v1", rank=8, iterations=5, reg=0.1)
write_manifest("als", "als-v1", ["als.pkl"], {"rank": 8, "iterations": 5, "reg": 0.1})
print("ALS OK\n")

# ----- Cold Start -----
print("=== Cold Start ===")
from recommender.student import cold_start
cold_start.train("business", MODELS / "cold-start-v1")
write_manifest("cold_start", "cold-start-v1", ["popular.pkl"], {"strategy": "popular+content_blend"})
print("Cold Start OK\n")

print("ALL DONE")
