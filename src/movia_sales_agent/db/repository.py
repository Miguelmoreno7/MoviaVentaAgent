from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

from movia_sales_agent.config.knowledge import load_policies_seed, load_products_seed
from movia_sales_agent.config.settings import Settings


class MoviaRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._offline_leads: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._offline_leads_by_id: Dict[str, Dict[str, Any]] = {}
        self._offline_meta_events: set[Tuple[str, str]] = set()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.database_url and not self.settings.disable_database)

    @contextmanager
    def connect(self):
        if not self.enabled:
            raise RuntimeError("Database is not configured")
        with psycopg.connect(self.settings.database_url, row_factory=dict_row) as conn:
            yield conn

    def fetch_products(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return load_products_seed()
        with self.connect() as conn:
            rows = conn.execute(
                """
                select p.*,
                  coalesce(
                    jsonb_agg(
                      jsonb_build_object(
                        'feature_type', f.feature_type,
                        'position', f.position,
                        'content', f.content,
                        'metadata', f.metadata
                      )
                      order by f.feature_type, f.position
                    ) filter (where f.id is not null),
                    '[]'::jsonb
                  ) as features
                from public.movia_products p
                left join public.movia_product_features f on f.product_id = p.id
                group by p.id
                order by p.setup_price_mxn nulls last
                """
            ).fetchall()
        return rows

    def fetch_policies(self) -> Dict[str, Any]:
        if not self.enabled:
            return load_policies_seed()
        with self.connect() as conn:
            rows = conn.execute(
                """
                select slug, title, policy_type, status, content, data
                from public.movia_policies
                order by policy_type, slug
                """
            ).fetchall()
        return {row["slug"]: row for row in rows}

    def fetch_platform_context(self) -> Dict[str, Any]:
        return {
            "official_links": self.fetch_official_links(),
            "project_statuses": self.fetch_project_statuses(),
        }

    def fetch_official_links(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return [
                {
                    "slug": "movia_app",
                    "label": "MovIA App",
                    "url": "https://app.moviatech.com.mx",
                    "link_type": "app",
                }
            ]
        with self.connect() as conn:
            return conn.execute(
                "select slug, label, url, link_type, status from public.movia_official_links"
            ).fetchall()

    def fetch_project_statuses(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        with self.connect() as conn:
            return conn.execute(
                """
                select slug, label, position, description, is_terminal
                from public.movia_project_statuses
                order by position
                """
            ).fetchall()

    def upsert_lead(self, channel: str, external_user_id: str) -> Dict[str, Any]:
        if not self.enabled:
            key = (channel, external_user_id)
            if key not in self._offline_leads:
                lead_id = f"offline:{channel}:{external_user_id}"
                now = utc_now_iso()
                self._offline_leads[key] = {
                    "id": lead_id,
                    "channel": channel,
                    "external_user_id": external_user_id,
                    "current_stage": "new",
                    "conversation_mode": "normal",
                    "previous_stage": None,
                    "stage_before_objection": None,
                    "stage_reason_code": None,
                    "stage_reason": None,
                    "stage_entered_at": now,
                    "stage_updated_at": now,
                    "active_objection": {},
                    "last_action": None,
                    "chatwoot_conversation_id": None,
                    "meta_ctwa_clid": None,
                    "meta_ctwa_clid_received_at": None,
                    "meta_referral": {},
                    "profile_data": {},
                }
                self._offline_leads_by_id[lead_id] = self._offline_leads[key]
            return copy_lead(self._offline_leads[key])
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into public.movia_lead_profiles (channel, external_user_id)
                values (%s, %s)
                on conflict (channel, external_user_id)
                do update set updated_at = now()
                returning *
                """,
                (channel, external_user_id),
            ).fetchone()
        return row

    def update_lead_profile(
        self,
        lead_id: Optional[str],
        updates: Dict[str, Any],
        current_stage: Optional[str] = None,
        previous_stage: Optional[str] = None,
        stage_before_objection: Optional[str] = None,
        stage_reason_code: Optional[str] = None,
        stage_reason: Optional[str] = None,
        conversation_mode: Optional[str] = None,
        stage_changed: bool = False,
        active_objection: Optional[Dict[str, Any]] = None,
        last_action: Optional[str] = None,
    ) -> None:
        if not self.enabled:
            self._update_offline_lead(
                lead_id,
                updates,
                current_stage=current_stage,
                previous_stage=previous_stage,
                stage_before_objection=stage_before_objection,
                stage_reason_code=stage_reason_code,
                stage_reason=stage_reason,
                conversation_mode=conversation_mode,
                stage_changed=stage_changed,
                active_objection=active_objection,
                last_action=last_action,
            )
            return
        if not lead_id:
            return
        allowed = {"business_type", "main_channel", "pain", "urgency", "buying_signal"}
        assignments = []
        values: List[Any] = []
        for key in allowed:
            value = updates.get(key)
            if value:
                assignments.append(f"{key} = %s")
                values.append(value)
        if current_stage:
            assignments.append("current_stage = %s")
            values.append(current_stage)
            assignments.append("stage_updated_at = now()")
            if stage_changed:
                assignments.append("stage_entered_at = now()")
        if previous_stage:
            assignments.append("previous_stage = %s")
            values.append(previous_stage)
        if stage_before_objection:
            assignments.append("stage_before_objection = %s")
            values.append(stage_before_objection)
        if stage_reason_code:
            assignments.append("stage_reason_code = %s")
            values.append(stage_reason_code)
        if stage_reason:
            assignments.append("stage_reason = %s")
            values.append(stage_reason)
        if conversation_mode:
            assignments.append("conversation_mode = %s")
            values.append(conversation_mode)
        if active_objection is not None:
            assignments.append("active_objection = %s::jsonb")
            values.append(json.dumps(active_objection))
        if last_action:
            assignments.append("last_action = %s")
            values.append(last_action)
        if updates.get("profile_data"):
            assignments.append("profile_data = profile_data || %s::jsonb")
            values.append(json.dumps(updates["profile_data"]))
        if not assignments:
            return
        values.append(lead_id)
        with self.connect() as conn:
            conn.execute(
                f"update public.movia_lead_profiles set {', '.join(assignments)} where id = %s",
                values,
            )

    def _update_offline_lead(
        self,
        lead_id: Optional[str],
        updates: Dict[str, Any],
        *,
        current_stage: Optional[str] = None,
        previous_stage: Optional[str] = None,
        stage_before_objection: Optional[str] = None,
        stage_reason_code: Optional[str] = None,
        stage_reason: Optional[str] = None,
        conversation_mode: Optional[str] = None,
        stage_changed: bool = False,
        active_objection: Optional[Dict[str, Any]] = None,
        last_action: Optional[str] = None,
    ) -> None:
        if not lead_id:
            return
        lead = self._offline_leads_by_id.get(lead_id)
        if not lead:
            return
        for key in {"business_type", "main_channel", "pain", "urgency", "buying_signal"}:
            value = updates.get(key)
            if value:
                lead[key] = value
        if updates.get("profile_data"):
            lead["profile_data"] = {
                **dict(lead.get("profile_data") or {}),
                **updates["profile_data"],
            }
        now = utc_now_iso()
        if current_stage:
            if stage_changed:
                lead["stage_entered_at"] = now
            lead["current_stage"] = current_stage
            lead["stage_updated_at"] = now
        if previous_stage:
            lead["previous_stage"] = previous_stage
        if stage_before_objection:
            lead["stage_before_objection"] = stage_before_objection
        if stage_reason_code:
            lead["stage_reason_code"] = stage_reason_code
        if stage_reason:
            lead["stage_reason"] = stage_reason
        if conversation_mode:
            lead["conversation_mode"] = conversation_mode
        if active_objection is not None:
            lead["active_objection"] = dict(active_objection)
        if last_action:
            lead["last_action"] = last_action

    def get_lead_profile(self, lead_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not lead_id:
            return None
        if not self.enabled:
            lead = self._offline_leads_by_id.get(lead_id)
            return copy_lead(lead) if lead else None
        with self.connect() as conn:
            row = conn.execute(
                "select * from public.movia_lead_profiles where id = %s",
                (lead_id,),
            ).fetchone()
        return row

    def update_chatwoot_conversation_id(
        self,
        lead_id: Optional[str],
        conversation_id: Optional[int],
    ) -> None:
        if not lead_id or not conversation_id:
            return
        if not self.enabled:
            lead = self._offline_leads_by_id.get(lead_id)
            if lead is not None:
                lead["chatwoot_conversation_id"] = int(conversation_id)
            return
        with self.connect() as conn:
            conn.execute(
                """
                update public.movia_lead_profiles
                set chatwoot_conversation_id = %s
                where id = %s
                """,
                (int(conversation_id), lead_id),
            )

    def store_meta_ctwa_attribution(
        self,
        lead_id: Optional[str],
        ctwa_clid: Optional[str],
        referral: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not lead_id or not ctwa_clid:
            return False
        if not self.enabled:
            lead = self._offline_leads_by_id.get(lead_id)
            if lead is None:
                return False
            if lead.get("meta_ctwa_clid"):
                return False
            lead["meta_ctwa_clid"] = str(ctwa_clid)
            lead["meta_ctwa_clid_received_at"] = utc_now_iso()
            lead["meta_referral"] = dict(referral or {})
            return True
        with self.connect() as conn:
            row = conn.execute(
                """
                update public.movia_lead_profiles
                set meta_ctwa_clid = %s,
                    meta_ctwa_clid_received_at = coalesce(meta_ctwa_clid_received_at, now()),
                    meta_referral = case
                      when coalesce(meta_referral, '{}'::jsonb) = '{}'::jsonb
                        then %s::jsonb
                      else meta_referral
                    end
                where id = %s
                  and meta_ctwa_clid is null
                returning id
                """,
                (str(ctwa_clid), json.dumps(referral or {}), lead_id),
            ).fetchone()
        return bool(row)

    def get_meta_ctwa_attribution(self, lead_id: Optional[str]) -> Dict[str, Any]:
        if not lead_id:
            return {}
        if not self.enabled:
            lead = self._offline_leads_by_id.get(lead_id) or {}
            return {
                "ctwa_clid": lead.get("meta_ctwa_clid"),
                "referral": lead.get("meta_referral") or {},
            }
        with self.connect() as conn:
            row = conn.execute(
                """
                select meta_ctwa_clid as ctwa_clid, meta_referral as referral
                from public.movia_lead_profiles
                where id = %s
                """,
                (lead_id,),
            ).fetchone()
        return dict(row or {})

    def create_meta_conversion_event(
        self,
        *,
        lead_id: Optional[str],
        event_name: str,
        event_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        if not lead_id:
            return False
        if not self.enabled:
            key = (lead_id, event_name)
            if key in self._offline_meta_events:
                return False
            self._offline_meta_events.add(key)
            return True
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into public.movia_meta_conversion_events (
                  lead_id, event_name, event_id, status, payload
                )
                values (%s, %s, %s, 'pending', %s::jsonb)
                on conflict (lead_id, event_name) do nothing
                returning id
                """,
                (lead_id, event_name, event_id, json.dumps(payload)),
            ).fetchone()
        return bool(row)

    def mark_meta_conversion_event_sent(
        self,
        *,
        event_id: str,
        response_json: Dict[str, Any],
    ) -> None:
        if not self.enabled:
            return
        with self.connect() as conn:
            conn.execute(
                """
                update public.movia_meta_conversion_events
                set status = 'sent',
                    response_json = %s::jsonb,
                    sent_at = now(),
                    last_attempted_at = now(),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                where event_id = %s
                """,
                (json.dumps(response_json), event_id),
            )

    def mark_meta_conversion_event_failed(self, *, event_id: str, error_text: str) -> None:
        if not self.enabled:
            return
        with self.connect() as conn:
            conn.execute(
                """
                update public.movia_meta_conversion_events
                set status = 'failed',
                    error_text = %s,
                    last_attempted_at = now(),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                where event_id = %s
                """,
                (error_text[:1000], event_id),
            )

    def load_recent_messages(self, lead_id: Optional[str], limit: int = 8) -> List[Dict[str, Any]]:
        if not self.enabled or not lead_id:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                """
                select role, content, created_at
                from public.movia_conversation_messages
                where lead_id = %s
                order by created_at desc
                limit %s
                """,
                (lead_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def save_message(
        self,
        lead_id: Optional[str],
        role: str,
        content: str,
        external_message_id: Optional[str] = None,
        analysis: Optional[Dict[str, Any]] = None,
        retrieval_metadata: Optional[Dict[str, Any]] = None,
        token_usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled or not lead_id:
            return
        with self.connect() as conn:
            conn.execute(
                """
                insert into public.movia_conversation_messages (
                  lead_id, external_message_id, role, content, analysis,
                  retrieval_metadata, token_usage
                )
                values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                on conflict do nothing
                """,
                (
                    lead_id,
                    external_message_id,
                    role,
                    content,
                    json.dumps(analysis or {}),
                    json.dumps(retrieval_metadata or {}),
                    json.dumps(token_usage or {}),
                ),
            )

    def message_exists(self, external_message_id: Optional[str]) -> bool:
        if not self.enabled or not external_message_id:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                select 1
                from public.movia_conversation_messages
                where external_message_id = %s
                limit 1
                """,
                (external_message_id,),
            ).fetchone()
        return bool(row)

    def match_knowledge(
        self, embedding: Iterable[float], match_count: int = 5, metadata_filter: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
        with self.connect() as conn:
            return conn.execute(
                """
                select *
                from public.match_movia_knowledge(%s::vector, %s, %s::jsonb)
                """,
                (vector_literal, match_count, json.dumps(metadata_filter or {})),
            ).fetchall()


def copy_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(lead)
    copied["profile_data"] = dict(lead.get("profile_data") or {})
    copied["active_objection"] = dict(lead.get("active_objection") or {})
    return copied


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
