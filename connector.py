"""
ARFA AOL — FHIR R4 Connector (Rung 1).

Reads from any FHIR R4 server (Synthea-loaded HAPI here, eventually the SMART
Health IT sandbox and Epic) via standard REST, and maps Patient/Appointment/
Encounter/Immunization into ARFA's canonical patient/appointment/treatment
store. Same canonical dict shape as `../manual-csv/connector.py` so AOL
modules consume both interchangeably.

Read-only by design for Rung 1. SMART/OAuth2 (Backend Services flow) is
Rung 2; see README.md.

Claim discipline: this is FHIR-standards capability validated on synthetic
data in a sandbox. Not a production EHR integration.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FhirConfig:
    base_url: str                       # e.g. "http://localhost:8080/fhir"
    env: str = "sandbox"                # sandbox | production
    timeout_s: int = 30
    page_size: int = 100
    tag: Optional[str] = None           # optional `_tag` filter (system|code) to scope reads on a shared server
    user_agent: str = "ARFA-AOL-FHIR-Connector/0.1"
    # No auth fields. HAPI sandbox is open. Rung 2 adds SMART Backend Services.


class FhirR4Connector:
    """FHIR R4 REST client. Paginated search for Patient/Appointment/Encounter/
    Immunization, mapped to ARFA canonical dicts (same fields as `manual-csv`).
    """

    def __init__(self, config: FhirConfig):
        if config.env not in ("sandbox", "production"):
            raise ValueError(f"env must be sandbox|production, got {config.env!r}")
        self.cfg = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "User-Agent": config.user_agent,
        })

    # ------------------------- HTTP / pagination -------------------------

    def _get(self, url: str) -> dict:
        log.debug("FHIR GET %s", url)
        r = self.session.get(url, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        return r.json()

    def _search(self, resource: str, params: Optional[dict] = None) -> Iterator[dict]:
        """Yield every resource matching a FHIR search, following the
        Bundle `link[next]` URL until exhausted."""
        params = dict(params or {})
        params.setdefault("_count", self.cfg.page_size)
        if self.cfg.tag:
            params.setdefault("_tag", self.cfg.tag)
        base = self.cfg.base_url.rstrip("/") + "/"
        url = urljoin(base, resource)
        first = True
        while url:
            request_url = url + (("?" + _qs(params)) if first else "")
            first = False
            bundle = self._get(request_url)
            for entry in bundle.get("entry") or []:
                res = entry.get("resource")
                if res:
                    yield res
            url = _next_link(bundle)

    # ------------------------- public reads -------------------------

    def import_patients(self) -> Iterator[dict]:
        for p in self._search("Patient"):
            yield _map_patient(p)

    def import_appointments(self, since: Optional[datetime] = None) -> Iterator[dict]:
        params = {}
        if since:
            params["date"] = f"ge{since.date().isoformat()}"
        for a in self._search("Appointment", params):
            yield _map_appointment(a)

    def import_treatments(self, since: Optional[datetime] = None) -> Iterator[dict]:
        """ARFA 'treatments' = FHIR Encounter (a visit/treatment event).
        Synthea is primary-care so this is general encounters; for an
        aesthetic practice the same mapping carries injection/laser visits."""
        params = {}
        if since:
            params["date"] = f"ge{since.date().isoformat()}"
        for e in self._search("Encounter", params):
            yield _map_encounter(e)

    def import_immunizations(self) -> Iterator[dict]:
        for i in self._search("Immunization"):
            yield _map_immunization(i)

    def subscribe_events(self) -> dict:
        # FHIR Subscriptions (n8n Rule 45) deferred to Rung 2.
        return {"mode": "poll", "reason": "Rung 1 polls; FHIR Subscriptions are Rung 2."}

    def read_raw(self, resource_type: str, params: Optional[dict] = None) -> Iterator[dict]:
        """Yield RAW (unmapped) FHIR resources. Used by the US Core conformance
        pre-check, which needs the original resource, not the ARFA mapping."""
        yield from self._search(resource_type, params)

    # ----- Level 1: write-back + delta sync -----
    def create_resource(self, resource_type: str, body: dict) -> dict:
        """POST a new FHIR resource (write-back). Returns the server's created
        resource, including its assigned id. Closes the loop: read -> decide -> act."""
        url = self.cfg.base_url.rstrip("/") + "/" + resource_type
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
            "User-Agent": self.cfg.user_agent,
        }
        r = requests.post(url, json=body, headers=headers, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        return r.json()

    def read_since(self, resource_type: str, since_iso: str,
                   params: Optional[dict] = None) -> Iterator[dict]:
        """Yield resources changed since `since_iso` via FHIR `_lastUpdated=gt...`.
        This is delta sync by polling; true push is FHIR Subscriptions (Rule 45),
        which needs a callback receiver and is a later increment."""
        p = dict(params or {})
        p["_lastUpdated"] = "gt" + since_iso
        yield from self._search(resource_type, p)


# ------------------------- mappers (FHIR -> ARFA canonical) -------------------------

def _map_patient(p: dict) -> dict:
    name = (p.get("name") or [{}])[0]
    family = name.get("family") or ""
    given = " ".join(name.get("given") or [])
    phone = ""
    for t in p.get("telecom") or []:
        if t.get("system") == "phone":
            phone = t.get("value", "")
            break
    return {
        "source_emr_id":     p.get("id", ""),
        "name_display":      f"{given} {family}".strip(),
        "dob_hash":          _hash(p.get("birthDate", "")) if p.get("birthDate") else "",
        "gender":            p.get("gender", ""),
        "phone":             phone,
        "marketing_consent": False,  # FHIR does not carry this; default false until learned
        "_source":           "fhir-r4",
    }


def _map_appointment(a: dict) -> dict:
    patient_ref = ""
    for part in a.get("participant") or []:
        ref = (part.get("actor") or {}).get("reference") or ""
        if ref.startswith("Patient/"):
            patient_ref = ref.split("/", 1)[1]
            break
    return {
        "source_emr_id": a.get("id", ""),
        "patient_key":   patient_ref,
        "provider":      "",  # Practitioner ref; deferred to later session
        "type":          _first_coding_display(a.get("serviceType", [{}])[0] if a.get("serviceType") else None),
        "status":        a.get("status", ""),
        "scheduled_at":  a.get("start", ""),
        "_source":       "fhir-r4",
    }


def _map_encounter(e: dict) -> dict:
    patient_ref = (e.get("subject") or {}).get("reference") or ""
    if patient_ref.startswith("Patient/"):
        patient_ref = patient_ref.split("/", 1)[1]
    period = e.get("period") or {}
    type_list = e.get("type") or []
    treatment_type = _first_coding_display(type_list[0]) if type_list else ""
    return {
        "source_emr_id":   e.get("id", ""),
        "appointment_key": "",  # FHIR does not always link Appointment<->Encounter
        "patient_key":     patient_ref,
        "treatment_type":  treatment_type,
        "molecule":        "",
        "units":           None,
        "area":            "",
        "treatment_at":    period.get("start", ""),
        "_source":         "fhir-r4",
    }


def _map_immunization(i: dict) -> dict:
    patient_ref = (i.get("patient") or {}).get("reference") or ""
    if patient_ref.startswith("Patient/"):
        patient_ref = patient_ref.split("/", 1)[1]
    return {
        "source_emr_id": i.get("id", ""),
        "patient_key":   patient_ref,
        "vaccine":       _first_coding_display(i.get("vaccineCode")),
        "occurrence":    i.get("occurrenceDateTime", ""),
        "_source":       "fhir-r4",
    }


# ------------------------- helpers -------------------------

def _qs(params: dict) -> str:
    return "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))


def _next_link(bundle: dict) -> Optional[str]:
    for link in bundle.get("link") or []:
        if link.get("relation") == "next":
            return link.get("url")
    return None


def _first_coding_display(codeable: Optional[dict]) -> str:
    if not codeable:
        return ""
    codings = codeable.get("coding") or []
    if not codings:
        return codeable.get("text", "")
    c = codings[0]
    return c.get("display") or c.get("code") or ""


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
