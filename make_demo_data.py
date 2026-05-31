"""
Generate a small, tag-scoped FHIR R4 transaction bundle for the Rung 1 demo.

This is a SMOKE-TEST FIXTURE, not Synthea. It exists so the demo produces a
meaningful follow-up table (all three recall buckets) without depending on a
large Synthea download. For the public/blog artifact, swap in real Synthea via
`load_synthea.py --tag ...`; the connector + scoring code is identical.

Patients are stamped with meta.tag = TAG so they can be read back in isolation
on a shared FHIR server via `?_tag=system|code`.

Usage:
    python make_demo_data.py
    # then:
    python load_synthea.py --dir synthea_data --base https://hapi.fhir.org/baseR4
    python demo.py --base https://hapi.fhir.org/baseR4 --tag "http://arfa-demo.test/run|aol-demo"
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

TAG_SYSTEM = "http://arfa-demo.test/run"
TAG_CODE = "aol-demo"
TAG = {"system": TAG_SYSTEM, "code": TAG_CODE}

NOW = datetime.now(timezone.utc)

# (family, given, gender, birth_year, [encounter offsets in days-ago]) designed
# to land across all three buckets given a 365-day recall window.
PEOPLE = [
    ("Gonzalez", "Maria",  "female", 1972, [800, 500, 400]),         # Needs call (last 400d > 365)
    ("Carter",   "James",  "male",   1985, [200, 170, 140, 110, 90]),# Soft touch (cadence ~30, last 90)
    ("Khan",     "Aisha",  "female", 1990, [60, 30, 15]),            # No action (within cadence)
    ("Lee",      "Robert", "male",   1968, [500]),                   # Needs call (single, 500d)
    ("Park",     "Linda",  "female", 1979, [120, 60]),               # No action (cadence 60, last 60)
    ("Nguyen",   "David",  "male",   1995, [400, 380]),              # Needs call (last 380d > 365)
    ("Davis",    "Emily",  "female", 2001, [50, 25]),                # No action (cadence 25, last 25)
    ("Miller",   "Frank",  "male",   1960, [200, 160, 100]),         # Soft touch (cadence ~50, last 100)
]


def _iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def build_bundle() -> dict:
    entries = []
    for idx, (family, given, gender, birth_year, offsets) in enumerate(PEOPLE, start=1):
        pid = str(uuid.uuid4())
        patient = {
            "resourceType": "Patient",
            "meta": {"tag": [dict(TAG)]},
            "identifier": [{"system": "http://arfa-demo.test/mrn", "value": f"AOL-{idx:03d}"}],
            "name": [{"family": family, "given": [given]}],
            "gender": gender,
            "birthDate": f"{birth_year}-01-15",
            "telecom": [{"system": "phone", "value": f"+1555010{idx:04d}"}],
        }
        entries.append({
            "fullUrl": f"urn:uuid:{pid}",
            "resource": patient,
            "request": {"method": "POST", "url": "Patient"},
        })
        for off in offsets:
            eid = str(uuid.uuid4())
            encounter = {
                "resourceType": "Encounter",
                "meta": {"tag": [dict(TAG)]},
                "status": "finished",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "AMB", "display": "ambulatory",
                },
                "type": [{"coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "162673000", "display": "General examination of patient",
                }]}],
                "subject": {"reference": f"urn:uuid:{pid}"},
                "period": {"start": _iso(off), "end": _iso(off)},
            }
            entries.append({
                "fullUrl": f"urn:uuid:{eid}",
                "resource": encounter,
                "request": {"method": "POST", "url": "Encounter"},
            })
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def main():
    out_dir = Path(__file__).parent / "synthea_data"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "arfa_demo.json"
    bundle = build_bundle()
    out_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    n_pat = sum(1 for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient")
    n_enc = sum(1 for e in bundle["entry"] if e["resource"]["resourceType"] == "Encounter")
    print(f"Wrote {out_file} ({n_pat} patients, {n_enc} encounters)")
    print(f"Tag for reads:  --tag \"{TAG_SYSTEM}|{TAG_CODE}\"")


if __name__ == "__main__":
    main()
