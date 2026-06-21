from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

from movia_sales_agent.config.paths import CONFIG_ROOT, RAG_DOCS_ROOT


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def load_config_bundle() -> Dict[str, Any]:
    bundle: Dict[str, Any] = {}
    for path in sorted(CONFIG_ROOT.glob("*.json")):
        bundle[path.stem] = read_json(path)
    return bundle


def load_products_seed() -> List[Dict[str, Any]]:
    products = read_json(CONFIG_ROOT / "products.seed.json")
    if not isinstance(products, list):
        raise ValueError("products.seed.json must contain a list")
    return products


def load_policies_seed() -> Dict[str, Any]:
    policies = read_json(CONFIG_ROOT / "policies.seed.json")
    if not isinstance(policies, dict):
        raise ValueError("policies.seed.json must contain an object")
    return policies


def iter_rag_documents() -> Iterable[Path]:
    yield from sorted(path for path in RAG_DOCS_ROOT.rglob("*.md") if path.is_file())

