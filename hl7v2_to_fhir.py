"""
Level 2: HL7 v2 ORU^R01 (lab result) -> FHIR R4 bridge.

Parses a pipe-delimited ORU^R01 message and maps it to the FHIR lab triad:
Patient + ServiceRequest (the order) + DiagnosticReport (the panel) + an
Observation per result, with LOINC codes, units, reference range, and abnormal
interpretation. This is the bridge most labs and hospitals actually run on
(HL7 v2 messaging in, FHIR out).

No external HL7 library: a focused parser for the segments an ORU uses
(MSH / PID / OBR / OBX). Synthetic messages only.
"""

from __future__ import annotations

import uuid

LOINC = "http://loinc.org"
# OBX-8 abnormal flag -> FHIR v3 ObservationInterpretation
V2_INTERP = {
    "H": ("H", "High"), "L": ("L", "Low"), "N": ("N", "Normal"),
    "HH": ("HH", "Critical high"), "LL": ("LL", "Critical low"), "A": ("A", "Abnormal"),
}
INTERP_SYS = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"


def parse_segments(raw: str):
    """Split a v2 message into (segment_name, fields[]) tuples."""
    segs = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"):
        line = line.strip()
        if line:
            fields = line.split("|")
            segs.append((fields[0], fields))
    return segs


def _comp(field: str, i: int, default: str = "") -> str:
    """Return the i-th ^-delimited component of a v2 field."""
    parts = (field or "").split("^")
    return parts[i] if i < len(parts) else default


def _sys_uri(code: str) -> str:
    return LOINC if (code or "").upper() in ("LN", "LOINC") else (code or "")


def _coding(field: str) -> dict:
    return {"system": _sys_uri(_comp(field, 2)), "code": _comp(field, 0), "display": _comp(field, 1)}


def oru_to_fhir_bundle(raw: str, tag: dict | None = None) -> dict:
    """Map an ORU^R01 message to a FHIR R4 transaction Bundle."""
    segs = parse_segments(raw)
    meta = {"tag": [tag]} if tag else {}
    pid_url = "urn:uuid:" + str(uuid.uuid4())
    sr_url = "urn:uuid:" + str(uuid.uuid4())
    dr_url = "urn:uuid:" + str(uuid.uuid4())

    patient = None
    panel = None
    obs_entries = []
    obs_refs = []

    for name, f in segs:
        if name == "PID":
            ident = f[3] if len(f) > 3 else ""
            nm = f[5] if len(f) > 5 else ""
            dob = f[7] if len(f) > 7 else ""
            sex = f[8] if len(f) > 8 else ""
            patient = {
                "resourceType": "Patient",
                "meta": dict(meta),
                "identifier": ([{"system": "urn:mrn", "value": _comp(ident, 0)}] if _comp(ident, 0) else []),
                "name": ([{"family": _comp(nm, 0), "given": [_comp(nm, 1)]}] if nm else []),
                "gender": {"M": "male", "F": "female"}.get(sex, "unknown"),
            }
            if len(dob) >= 8:
                patient["birthDate"] = f"{dob[0:4]}-{dob[4:6]}-{dob[6:8]}"
        elif name == "OBR":
            panel = _coding(f[4]) if len(f) > 4 else {}
        elif name == "OBX":
            code = f[3] if len(f) > 3 else ""
            value = f[5] if len(f) > 5 else ""
            units = f[6] if len(f) > 6 else ""
            refrange = f[7] if len(f) > 7 else ""
            abnormal = f[8] if len(f) > 8 else ""
            status = f[11] if len(f) > 11 else "F"
            ouuid = "urn:uuid:" + str(uuid.uuid4())
            obs = {
                "resourceType": "Observation",
                "meta": dict(meta),
                "status": {"F": "final", "P": "preliminary", "C": "corrected"}.get(status, "final"),
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                          "code": "laboratory", "display": "Laboratory"}]}],
                "code": {"coding": [_coding(code)], "text": _comp(code, 1)},
                "subject": {"reference": pid_url},
            }
            try:
                obs["valueQuantity"] = {"value": float(value), "unit": units,
                                        "system": "http://unitsofmeasure.org", "code": units}
            except (ValueError, TypeError):
                obs["valueString"] = value
            if refrange:
                obs["referenceRange"] = [{"text": refrange}]
            if abnormal in V2_INTERP:
                ic, idisp = V2_INTERP[abnormal]
                obs["interpretation"] = [{"coding": [{"system": INTERP_SYS, "code": ic, "display": idisp}]}]
            obs_entries.append({"fullUrl": ouuid, "resource": obs, "request": {"method": "POST", "url": "Observation"}})
            obs_refs.append({"reference": ouuid})

    service_request = {
        "resourceType": "ServiceRequest", "meta": dict(meta),
        "status": "completed", "intent": "order",
        "code": {"coding": [panel]} if panel else {},
        "subject": {"reference": pid_url},
    }
    diagnostic_report = {
        "resourceType": "DiagnosticReport", "meta": dict(meta),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                                  "code": "LAB", "display": "Laboratory"}]}],
        "code": {"coding": [panel], "text": panel.get("display", "")} if panel else {},
        "subject": {"reference": pid_url},
        "basedOn": [{"reference": sr_url}],
        "result": obs_refs,
    }

    entries = []
    if patient:
        entries.append({"fullUrl": pid_url, "resource": patient, "request": {"method": "POST", "url": "Patient"}})
    entries.append({"fullUrl": sr_url, "resource": service_request, "request": {"method": "POST", "url": "ServiceRequest"}})
    entries.extend(obs_entries)
    entries.append({"fullUrl": dr_url, "resource": diagnostic_report, "request": {"method": "POST", "url": "DiagnosticReport"}})
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


# A synthetic ORU^R01: a comprehensive metabolic panel with one high glucose.
SAMPLE_ORU = (
    "MSH|^~\\&|LAB|HOSP|EHR|CLINIC|20260530120000||ORU^R01|MSG0001|P|2.5.1\n"
    "PID|1||MRN12345^^^HOSP^MR||Rivera^Sofia||19850315|F\n"
    "OBR|1||ORDER987|24323-8^Comprehensive metabolic panel^LN|||20260530100000\n"
    "OBX|1|NM|2345-7^Glucose^LN||118|mg/dL|70-99|H|||F\n"
    "OBX|2|NM|2160-0^Creatinine^LN||1.1|mg/dL|0.6-1.3|N|||F\n"
    "OBX|3|NM|3094-0^Urea nitrogen^LN||18|mg/dL|7-20|N|||F\n"
    "OBX|4|NM|2951-2^Sodium^LN||139|mmol/L|136-145|N|||F\n"
)
