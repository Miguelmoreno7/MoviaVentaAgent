from __future__ import annotations

import argparse
import json

from movia_sales_agent.platform.registry_sync import sync_from_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync MovIA agent registry to platform tables.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = sync_from_settings(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
