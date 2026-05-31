"""
Level 2 demo: HL7 v2 ORU^R01 -> FHIR R4 bridge, end to end.

Parses a synthetic lab result, maps it to the FHIR lab triad (Patient +
ServiceRequest + DiagnosticReport + Observations), loads it to a FHIR server as
a transaction, reads it back, and runs the US Core lab-Observation check.

Usage:
    python hl7v2_demo.py --base https://hapi.fhir.org/baseR4
"""

from __future__ import annotations

import argparse

import requests

import hl7v2_to_fhir as h
import us_core_check
from connector import FhirConfig, FhirR4Connector

TAG_SYSTEM = "http://arfa-demo.test/run"
TAG_CODE = "lab-demo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080/fhir")
    args = ap.parse_args()
    tag = {"system": TAG_SYSTEM, "code": TAG_CODE}

    print("1. parse ORU^R01 -> FHIR ...")
    bundle = h.oru_to_fhir_bundle(h.SAMPLE_ORU, tag=tag)
    counts = {}
    for e in bundle["entry"]:
        rt = e["resource"]["resourceType"]
        counts[rt] = counts.get(rt, 0) + 1
    print("   bundle:", ", ".join(f"{v} {k}" for k, v in counts.items()))

    print("2. load to FHIR server (transaction) ...")
    r = requests.post(args.base.rstrip("/"), json=bundle,
                      headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
                      timeout=30)
    print(f"   transaction -> HTTP {r.status_code}")
    r.raise_for_status()

    print("3. read back + US Core lab check ...")
    fhir = FhirR4Connector(FhirConfig(base_url=args.base, tag=f"{TAG_SYSTEM}|{TAG_CODE}"))
    dr = list(fhir.read_raw("DiagnosticReport"))
    obs = list(fhir.read_raw("Observation"))
    results = [us_core_check.validate(o) for o in obs]
    passed = sum(1 for x in results if x.ok)
    print(f"   DiagnosticReport: {len(dr)} | Observation: {len(obs)} | US Core lab pass: {passed}/{len(obs)}")
    for o in sorted(obs, key=lambda x: (x.get("code") or {}).get("text", "")):
        c = ((o.get("code") or {}).get("coding") or [{}])[0]
        v = o.get("valueQuantity", {})
        interp = (((o.get("interpretation") or [{}])[0].get("coding") or [{}])[0].get("code"))
        flag = f"  [{interp}]" if interp and interp != "N" else ""
        print(f"     {c.get('code')} {c.get('display')}: {v.get('value')} {v.get('unit')}{flag}")

    print("LEVEL2_HL7V2_BRIDGE_OK" if (dr and obs and passed == len(obs)) else "INCOMPLETE")


if __name__ == "__main__":
    main()
