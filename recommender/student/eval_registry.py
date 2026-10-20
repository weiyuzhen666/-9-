"""Register evaluation-mode providers (models/evaluation manifests) into PROVIDERS.

Import this module to make the contract selfcheck exercise the evaluation-mode
artifacts, e.g.:

    python -m recommender.check selfcheck --mode evaluation \
        --module recommender.student.eval_registry
"""
from pathlib import Path

from recommender.contracts import PROVIDERS, Algorithm

from .popular import PopularProvider
from .content import ContentProvider
from .itemcf import ItemCFProvider
from .als import ALSProvider
from .cold_start import ColdStartProvider
from .rrf import RRFProvider

MODELS = Path(__file__).resolve().parent.parent.parent / "models" / "evaluation"

PROVIDERS[Algorithm.popular] = PopularProvider(MODELS / "popular-v1" / "manifest.json")
PROVIDERS[Algorithm.content] = ContentProvider(MODELS / "content-v1" / "manifest.json")
PROVIDERS[Algorithm.itemcf] = ItemCFProvider(MODELS / "itemcf-v1" / "manifest.json")
PROVIDERS[Algorithm.als] = ALSProvider(MODELS / "als-v1" / "manifest.json")
PROVIDERS[Algorithm.cold_start] = ColdStartProvider(MODELS / "cold-start-v1" / "manifest.json")
PROVIDERS[Algorithm.rrf_fusion] = RRFProvider(MODELS / "rrf-v1" / "manifest.json")
