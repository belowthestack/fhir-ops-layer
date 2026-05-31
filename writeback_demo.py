"""
Level 1 demo: write-back + delta sync against a FHIR server.

Reads the recall list, logs a recall outreach (a FHIR `Communication`) for the
top "needs call" patient, reads it back, then proves delta sync (`_lastUpdated`)
catches the new write. Write-back closes the loop: read -> decide -> act.

Tag-scoped on the shared sandbox.

Usage:
    python writeback_demo.py --base https://hapi.fhir.org/baseR4 --tag "http://arfa-demo.test/run|aol-demo"
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict

from connector import FhirConfig, FhirR4Connector
from retention_scoring import score_patients

TAG_SYSTEM = "http://arfa-demo.test/run"
TAG_CODE = "aol-demo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/fhir")
    ap.add_argument("--tag", default=None, help="_tag filter (system|code)")
    args = ap.parse_args()
    fhir = FhirR4Connector(FhirConfig(base_url=args.base, tag=args.tag))

    # 1. read + score (same as Rung 1)
    print("1. read + score ...")
    patients = list(fhir.import_patients())
    encs = defaultdict(list)
    for e in fhir.import_treatments():
        if e["patient_key"]:
            encs[e["patient_key"]].append(e)
    items = score_patients(patients, encs)
    needs = [i for i in items if i.bucket == "Needs call this week"]
    if not needs:
        print("   no 'needs call' patients found; run make_demo_data.py + load_synthea.py first.")
        return
    top = needs[0]
    print(f"   top needs-call: {top.patient_name} ({top.patient_id}) - {top.explanation}")

    before = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=10)).isoformat()

    # 2. write-back: log a recall outreach as a FHIR Communication
    print("2. write-back: logging a recall outreach (Communication) ...")
    comm = {
        "resourceType": "Communication",
        "meta": {"tag": [{"system": TAG_SYSTEM, "code": TAG_CODE}]},
        "status": "completed",
        "category": [{
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/communication-category",
                        "code": "notification"}],
            "text": "recall outreach",
        }],
        "subject": {"reference": f"Patient/{top.patient_id}"},
        "sent": dt.datetime.now(dt.timezone.utc).isoformat(),
        "payload": [{"contentString": f"Recall reminder ({top.bucket}): {top.explanation}"}],
    }
    created = fhir.create_resource("Communication", comm)
    cid = created.get("id")
    print(f"   wrote Communication/{cid} for {top.patient_name}")

    # 3. read it back
    print("3. read it back ...")
    got = list(fhir.read_raw("Communication", {"_id": cid}))
    status = got[0].get("status") if got else "MISSING"
    subj = (got[0].get("subject") or {}).get("reference") if got else None
    print(f"   read back {len(got)} Communication, status={status}, subject={subj}")

    # 4. delta sync: what changed since `before`
    print("4. delta sync (_lastUpdated) ...")
    delta = list(fhir.read_since("Communication", before))
    caught = any(d.get("id") == cid for d in delta)
    print(f"   {len(delta)} Communication(s) changed since {before[:19]}Z; new write caught: {caught}")

    ok = bool(cid) and bool(got) and caught
    print("LEVEL1_WRITEBACK_OK" if ok else "INCOMPLETE")


if __name__ == "__main__":
    main()
