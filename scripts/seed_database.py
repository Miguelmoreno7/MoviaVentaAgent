#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
FALLBACK_ENV = Path("/Users/miguelmoreno/developer/Movia/MoviaVentaAgente/.env")
sys.path.insert(0, str(SRC_ROOT))

from movia_sales_agent.config.knowledge import load_policies_seed, load_products_seed  # noqa: E402


def load_env() -> None:
    if (PROJECT_ROOT / ".env").exists():
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    elif FALLBACK_ENV.exists():
        load_dotenv(FALLBACK_ENV, override=False)


def json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def upsert_product(conn, product: Dict[str, Any]) -> str:
    row = conn.execute(
        """
        insert into public.movia_products (
          slug, name, status, setup_price_mxn, monthly_price_mxn, delivery_time,
          included_meetings, short_description, source_path, approved
        )
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true)
        on conflict (slug) do update set
          name = excluded.name,
          status = excluded.status,
          setup_price_mxn = excluded.setup_price_mxn,
          monthly_price_mxn = excluded.monthly_price_mxn,
          delivery_time = excluded.delivery_time,
          included_meetings = excluded.included_meetings,
          short_description = excluded.short_description,
          source_path = excluded.source_path,
          approved = excluded.approved
        returning id
        """,
        (
            product["slug"],
            product["name"],
            product["status"],
            product.get("setup_price_mxn"),
            product.get("monthly_price_mxn"),
            product.get("delivery_time"),
            json_value(product.get("included_meetings") or {}),
            product.get("short_description"),
            "docs/movia_knowledge_source/config/products.seed.json",
        ),
    ).fetchone()
    product_id = row["id"]
    conn.execute("delete from public.movia_product_features where product_id = %s", (product_id,))
    for feature_type, source_key in (
        ("include", "includes"),
        ("exclude", "excludes"),
        ("recommended_when", "recommended_when"),
    ):
        for position, content in enumerate(product.get(source_key) or []):
            conn.execute(
                """
                insert into public.movia_product_features (
                  product_id, feature_type, position, content, source_path
                )
                values (%s, %s, %s, %s, %s)
                """,
                (
                    product_id,
                    feature_type,
                    position,
                    content,
                    "docs/movia_knowledge_source/config/products.seed.json",
                ),
            )
    return str(product_id)


def seed_policies(conn) -> None:
    policies = load_policies_seed()
    policy_titles = {
        "deposit": "Depósito inicial",
        "final_payment": "Pago restante",
        "refund_policy": "Política de no reembolso",
        "monthly_billing": "Mensualidad",
        "api_tokens": "Tokens y uso de API",
    }
    for slug, data in policies.items():
        content = data.get("description") or data.get("overage_policy") or json_value(data)
        status = "official"
        if slug == "api_tokens":
            status = "policy_draft"
        conn.execute(
            """
            insert into public.movia_policies (
              slug, title, policy_type, status, content, data, source_path, approved
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s, true)
            on conflict (slug) do update set
              title = excluded.title,
              policy_type = excluded.policy_type,
              status = excluded.status,
              content = excluded.content,
              data = excluded.data,
              source_path = excluded.source_path,
              approved = excluded.approved
            """,
            (
                slug,
                policy_titles.get(slug, slug.replace("_", " ").title()),
                slug,
                status,
                content,
                json_value(data),
                "docs/movia_knowledge_source/config/policies.seed.json",
            ),
        )


def seed_reference_data(conn) -> None:
    conn.execute(
        """
        insert into public.movia_channels (slug, name, status, description, requirements, source_path)
        values
          ('whatsapp-business', 'WhatsApp Business', 'available',
           'Canal actualmente disponible para agentes MovIA.',
           '["Cuenta de WhatsApp Business", "Cuenta de Facebook vinculada", "Permisos suficientes en Meta"]'::jsonb,
           'docs/movia_knowledge_source/docs/04_channels_and_integrations.md'),
          ('facebook', 'Facebook', 'in_progress',
           'Canal en proceso; no debe venderse como producción.',
           '[]'::jsonb,
           'docs/movia_knowledge_source/docs/04_channels_and_integrations.md'),
          ('instagram', 'Instagram', 'in_progress',
           'Canal en proceso; no debe venderse como producción.',
           '[]'::jsonb,
           'docs/movia_knowledge_source/docs/04_channels_and_integrations.md')
        on conflict (slug) do update set
          name = excluded.name,
          status = excluded.status,
          description = excluded.description,
          requirements = excluded.requirements,
          source_path = excluded.source_path
        """
    )
    conn.execute(
        """
        insert into public.movia_integrations (
          slug, name, status, provider, description, requirements, source_path
        )
        values
          ('meta-whatsapp-official', 'Meta WhatsApp Business official connection', 'available',
           'Meta', 'MovIA utiliza la conexión oficial de Meta/Facebook para WhatsApp Business.',
           '["WhatsApp Business", "Cuenta de Facebook", "Permisos suficientes"]'::jsonb,
           'docs/movia_knowledge_source/docs/04_channels_and_integrations.md')
        on conflict (slug) do update set
          name = excluded.name,
          status = excluded.status,
          provider = excluded.provider,
          description = excluded.description,
          requirements = excluded.requirements,
          source_path = excluded.source_path
        """
    )
    conn.execute(
        """
        insert into public.movia_official_links (slug, label, url, link_type, source_path)
        values
          ('movia_app', 'MovIA App', 'https://app.moviatech.com.mx', 'app',
           'docs/movia_knowledge_source/docs/02_webapp_process.md')
        on conflict (slug) do update set
          label = excluded.label,
          url = excluded.url,
          link_type = excluded.link_type,
          source_path = excluded.source_path
        """
    )
    statuses = [
        ("pending", "Pendiente", 10, "Proyecto pendiente de inicio.", False),
        ("building", "En construcción", 20, "MovIA está construyendo el agente.", False),
        ("under_review", "En revisión", 30, "Cliente revisa pruebas y resultados.", False),
        ("approved", "Aprobado", 40, "Cliente aprobó el agente.", False),
        ("final_payment_pending", "Pendiente de pago final", 50, "Falta liquidar el restante.", False),
        ("active", "Activo", 60, "Agente desplegado en WhatsApp.", False),
        ("paused", "Pausado", 70, "Agente pausado por falta de pago u otra razón.", False),
        ("cancelled", "Cancelado", 80, "Proyecto cancelado.", True),
    ]
    for slug, label, position, description, is_terminal in statuses:
        conn.execute(
            """
            insert into public.movia_project_statuses (
              slug, label, position, description, is_terminal, source_path
            )
            values (%s, %s, %s, %s, %s, %s)
            on conflict (slug) do update set
              label = excluded.label,
              position = excluded.position,
              description = excluded.description,
              is_terminal = excluded.is_terminal,
              source_path = excluded.source_path
            """,
            (
                slug,
                label,
                position,
                description,
                is_terminal,
                "docs/movia_knowledge_source/docs/02_webapp_process.md",
            ),
        )


def main() -> int:
    load_env()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is missing; cannot seed database.", file=sys.stderr)
        return 1
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        for product in load_products_seed():
            upsert_product(conn, product)
        seed_policies(conn)
        seed_reference_data(conn)
    print("seed complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

