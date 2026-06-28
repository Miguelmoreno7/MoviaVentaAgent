from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional

import httpx

from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.meta.conversions import GRAPH_API_VERSION


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Manage MovIA Meta Business Messaging CAPI.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("get-dataset", help="Read the dataset linked to the WhatsApp Business Account.")
    create = subparsers.add_parser(
        "create-dataset",
        help="Create or return the dataset linked to the WhatsApp Business Account.",
    )
    create.add_argument("--name", default="MovIA WhatsApp Leads")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "get-dataset":
        print(json.dumps(get_dataset(settings), ensure_ascii=False, indent=2))
        return
    if args.command == "create-dataset":
        print(json.dumps(create_dataset(settings, args.name), ensure_ascii=False, indent=2))


def get_dataset(settings: Settings) -> Dict[str, Any]:
    _require_dataset_settings(settings)
    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{settings.meta_whatsapp_business_account_id}/dataset"
    )
    return _request("GET", url, settings)


def create_dataset(settings: Settings, name: str) -> Dict[str, Any]:
    _require_dataset_settings(settings)
    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{settings.meta_whatsapp_business_account_id}/dataset"
    )
    return _request("POST", url, settings, json_payload={"name": name})


def _request(
    method: str,
    url: str,
    settings: Settings,
    *,
    json_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {settings.meta_whatsapp_access_token}"}
    with httpx.Client(timeout=20) as client:
        response = client.request(method, url, headers=headers, json=json_payload)
        response.raise_for_status()
        return response.json()


def _require_dataset_settings(settings: Settings) -> None:
    missing = []
    if not settings.meta_whatsapp_access_token:
        missing.append("META_WHATSAPP_ACCESS_TOKEN")
    if not settings.meta_whatsapp_business_account_id:
        missing.append("META_WHATSAPP_BUSINESS_ACCOUNT_ID")
    if missing:
        raise SystemExit("Missing required env vars: " + ", ".join(missing))


if __name__ == "__main__":
    main()
