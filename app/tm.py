from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from app.store import store


DEFAULT_APPROVED_ENTRIES = [{
    "source": "Start Quote", "translation": "Iniciar cotización",
    "site_id": "het-main", "component": "CTA",
    "context": "Primary quote call-to-action", "locale": "es-US",
    "approved": True, "approved_by": "system-seed",
}]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(value: Optional[str], field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


class TranslationMemory:
    """Human-governed translation memory with immutable review audit events."""

    store_key = "translation_memory"

    def search(self, source: str, locale: str = "es-US", site_id: Optional[str] = None,
               component: Optional[str] = None) -> List[Dict[str, Any]]:
        source_key = _required(source, "source").casefold()
        locale_key = _required(locale, "locale").casefold()
        site_key = site_id.casefold() if site_id else None
        component_key = component.casefold() if component else None
        entries = list(store.load(self.store_key).get("entries", [])) + DEFAULT_APPROVED_ENTRIES
        matches = []
        for entry in entries:
            if not entry.get("approved"):
                continue
            if str(entry.get("source", "")).strip().casefold() != source_key:
                continue
            if str(entry.get("locale", "")).strip().casefold() != locale_key:
                continue
            if component_key and str(entry.get("component", "")).strip().casefold() != component_key:
                continue
            entry_site = str(entry.get("site_id") or "").casefold() or None
            if site_key and entry_site not in {site_key, None}:
                continue
            matches.append((0 if site_key and entry_site == site_key else 1, entry))
        matches.sort(key=lambda item: item[0])
        unique, seen = [], set()
        for _, entry in matches:
            key = tuple(str(entry.get(name) or "").casefold() for name in
                        ("source", "translation", "site_id", "component", "locale"))
            if key not in seen:
                seen.add(key)
                unique.append(entry)
        return unique[:5]

    def propose(self, source: str, translation: str, site_id: Optional[str] = None,
                component: Optional[str] = None, context: Optional[str] = None,
                locale: str = "es-US", notes: Optional[str] = None) -> Dict[str, Any]:
        proposal = {
            "proposal_id": str(uuid.uuid4()), "source": _required(source, "source"),
            "translation": _required(translation, "translation"), "site_id": site_id,
            "component": component, "context": context, "locale": _required(locale, "locale"),
            "notes": notes, "status": "proposed", "created_at": _now(),
            "reviewed_at": None, "reviewer": None,
        }

        def append(data):
            proposals = data.setdefault("proposals", [])
            duplicate = next((p for p in proposals if p.get("status") == "proposed" and all(
                str(p.get(k) or "").casefold() == str(proposal.get(k) or "").casefold()
                for k in ("source", "translation", "site_id", "component", "locale"))), None)
            if duplicate:
                raise ValueError(f"Duplicate open proposal: {duplicate['proposal_id']}")
            proposals.append(proposal)
            data.setdefault("entries", [])
            data.setdefault("audit", []).append({
                "event": "proposal_created", "proposal_id": proposal["proposal_id"], "at": _now()
            })

        store.mutate(self.store_key, append)
        return proposal

    def list_proposals(self, status: str = "proposed") -> List[Dict[str, Any]]:
        allowed = {"proposed", "approved", "rejected", "all"}
        if status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        proposals = store.load(self.store_key).get("proposals", [])
        return proposals if status == "all" else [p for p in proposals if p.get("status") == status]

    def _review(self, proposal_id: str, decision: str, reviewer: str,
                reason: Optional[str]) -> Dict[str, Any]:
        reviewer = _required(reviewer, "reviewer")
        result: Dict[str, Any] = {}

        def review(data):
            proposal = next((p for p in data.get("proposals", [])
                             if p.get("proposal_id") == proposal_id), None)
            if not proposal:
                raise ValueError(f"Proposal {proposal_id} not found")
            if proposal.get("status") != "proposed":
                raise ValueError(f"Proposal {proposal_id} was already {proposal.get('status')}")
            reviewed_at = _now()
            proposal.update({"status": decision, "reviewed_at": reviewed_at,
                             "reviewer": reviewer, "reason": reason})
            if decision == "approved":
                entry = {key: proposal.get(key) for key in
                         ("source", "translation", "site_id", "component", "context", "locale")}
                entry.update({"approved": True, "approved_by": reviewer, "approved_at": reviewed_at})
                keys = ("source", "translation", "site_id", "component", "locale")
                entry_key = tuple(str(entry.get(k) or "").casefold() for k in keys)
                entries = data.setdefault("entries", [])
                if not any(tuple(str(e.get(k) or "").casefold() for k in keys) == entry_key
                           for e in entries):
                    entries.append(entry)
            data.setdefault("audit", []).append({
                "event": f"proposal_{decision}", "proposal_id": proposal_id,
                "reviewer": reviewer, "reason": reason, "at": reviewed_at,
            })
            result.update(proposal)

        store.mutate(self.store_key, review)
        return result

    def approve_proposal(self, proposal_id: str, reviewer: str,
                         reason: Optional[str] = None) -> Dict[str, Any]:
        return self._review(proposal_id, "approved", reviewer, reason)

    def reject_proposal(self, proposal_id: str, reviewer: str,
                        reason: Optional[str] = None) -> Dict[str, Any]:
        return self._review(proposal_id, "rejected", reviewer, reason)
