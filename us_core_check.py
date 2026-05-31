"""
US Core 6.1.0 conformance PRE-CHECK (Rung 1, Session 2).

A lightweight, in-pipeline conformance gate: checks that the FHIR resources we
read carry the US Core required / must-support elements and use the expected
terminology systems.

IT IS NOT the authoritative validator. Official US Core profile validation is
HL7 `validator_cli.jar` + the US Core IG package, or ONC Inferno; both need
Java and run as a separate CI gate (deferred, no Java on this host yet).
Framing discipline: call this a "US Core conformance pre-check," never "fully
US Core validated."

Covers the resources this connector reads that HAVE US Core profiles:
Patient, Encounter, Immunization.
Appointment is intentionally NOT checked, US Core / USCDI does not profile it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Terminology systems US Core binds (subset we touch)
CVX = "http://hl7.org/fhir/sid/cvx"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
CPT = "http://www.ama-assn.org/go/cpt"
V3_ACTCODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    path: str
    message: str


@dataclass
class ConformanceResult:
    resource_type: str
    resource_id: str
    profile: str
    issues: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def check_patient(r: dict) -> ConformanceResult:
    issues: list[Issue] = []
    if not r.get("identifier"):
        issues.append(Issue("error", "Patient.identifier", "US Core Patient requires >=1 identifier"))
    else:
        for i, idn in enumerate(r["identifier"]):
            if not idn.get("system") or not idn.get("value"):
                issues.append(Issue("warning", f"Patient.identifier[{i}]", "identifier should carry system + value"))
    names = r.get("name") or []
    if not names:
        issues.append(Issue("error", "Patient.name", "US Core Patient requires >=1 name"))
    elif not names[0].get("family") and not names[0].get("given"):
        issues.append(Issue("error", "Patient.name[0]", "name must have family or given"))
    if not r.get("gender"):
        issues.append(Issue("error", "Patient.gender", "US Core Patient requires gender"))
    if not r.get("birthDate"):
        issues.append(Issue("warning", "Patient.birthDate", "US Core marks birthDate must-support"))
    return ConformanceResult("Patient", r.get("id", ""), "us-core-patient", issues)


def check_encounter(r: dict) -> ConformanceResult:
    issues: list[Issue] = []
    if not r.get("status"):
        issues.append(Issue("error", "Encounter.status", "required"))
    cls = r.get("class")
    if not cls:
        issues.append(Issue("error", "Encounter.class", "US Core Encounter requires class"))
    elif cls.get("system") != V3_ACTCODE:
        issues.append(Issue("warning", "Encounter.class.system", f"expected {V3_ACTCODE}"))
    types = r.get("type") or []
    if not types:
        issues.append(Issue("error", "Encounter.type", "US Core Encounter requires type"))
    else:
        codings = types[0].get("coding") or []
        if codings and codings[0].get("system") not in (SNOMED, CPT):
            issues.append(Issue("warning", "Encounter.type.coding.system", "expected SNOMED CT or CPT"))
    subj = (r.get("subject") or {}).get("reference", "")
    if not subj.startswith("Patient/"):
        issues.append(Issue("error", "Encounter.subject", "required reference to a Patient"))
    if not r.get("period"):
        issues.append(Issue("warning", "Encounter.period", "must-support"))
    return ConformanceResult("Encounter", r.get("id", ""), "us-core-encounter", issues)


def check_immunization(r: dict) -> ConformanceResult:
    issues: list[Issue] = []
    if not r.get("status"):
        issues.append(Issue("error", "Immunization.status", "required"))
    codings = (r.get("vaccineCode") or {}).get("coding") or []
    if not codings:
        issues.append(Issue("error", "Immunization.vaccineCode", "required"))
    elif not any(c.get("system") == CVX for c in codings):
        issues.append(Issue("warning", "Immunization.vaccineCode", "US Core expects a CVX code"))
    if not (r.get("patient") or {}).get("reference", "").startswith("Patient/"):
        issues.append(Issue("error", "Immunization.patient", "required reference to a Patient"))
    if not (r.get("occurrenceDateTime") or r.get("occurrenceString")):
        issues.append(Issue("error", "Immunization.occurrence[x]", "required"))
    return ConformanceResult("Immunization", r.get("id", ""), "us-core-immunization", issues)


def check_observation(r: dict) -> ConformanceResult:
    """US Core Laboratory Result Observation."""
    issues: list[Issue] = []
    if not r.get("status"):
        issues.append(Issue("error", "Observation.status", "required"))
    cats = r.get("category") or []
    has_lab = any(any(c.get("code") == "laboratory" for c in (cat.get("coding") or [])) for cat in cats)
    if not has_lab:
        issues.append(Issue("warning", "Observation.category", "US Core Lab Observation expects category=laboratory"))
    codings = (r.get("code") or {}).get("coding") or []
    if not codings:
        issues.append(Issue("error", "Observation.code", "required"))
    elif not any(c.get("system") == LOINC for c in codings):
        issues.append(Issue("warning", "Observation.code", "US Core Lab Observation expects a LOINC code"))
    if not (r.get("subject") or {}).get("reference", "").startswith("Patient/"):
        issues.append(Issue("error", "Observation.subject", "required reference to a Patient"))
    has_value = any(k in r for k in ("valueQuantity", "valueString", "valueCodeableConcept", "valueBoolean", "valueInteger")) or r.get("dataAbsentReason")
    if not has_value:
        issues.append(Issue("error", "Observation.value[x]", "required (or dataAbsentReason)"))
    return ConformanceResult("Observation", r.get("id", ""), "us-core-observation-lab", issues)


CHECKERS = {
    "Patient": check_patient,
    "Encounter": check_encounter,
    "Immunization": check_immunization,
    "Observation": check_observation,
}


def validate(resource: dict) -> ConformanceResult:
    rt = resource.get("resourceType", "")
    checker = CHECKERS.get(rt)
    if not checker:
        # No US Core profile for this type (e.g. Appointment) - structural only.
        return ConformanceResult(rt, resource.get("id", ""), "(no US Core profile)", [])
    return checker(resource)
