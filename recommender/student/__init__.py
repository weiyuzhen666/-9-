"""Student recommender module — algorithm provider registry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MODELS = ROOT / "models" / "business"

from recommender.contracts import PROVIDERS, Algorithm

from .popular import PopularProvider
from .content import ContentProvider
from .itemcf import ItemCFProvider
from .als import ALSProvider
from .cold_start import ColdStartProvider

PROVIDERS[Algorithm.popular] = PopularProvider(MODELS / "popular-v1" / "manifest.json")
PROVIDERS[Algorithm.content] = ContentProvider(MODELS / "content-v1" / "manifest.json")
PROVIDERS[Algorithm.itemcf] = ItemCFProvider(MODELS / "itemcf-v1" / "manifest.json")
PROVIDERS[Algorithm.als] = ALSProvider(MODELS / "als-v1" / "manifest.json")
PROVIDERS[Algorithm.cold_start] = ColdStartProvider(MODELS / "cold-start-v1" / "manifest.json")
