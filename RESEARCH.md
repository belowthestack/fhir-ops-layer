# RESEARCH — FHIR R4 Connector design notes

## Standards posture
- **FHIR R4** (the version every certified US EHR exposes under ONC / 21st Century Cures rules).
- **US Core 6.1.0** profiles for resource fields, planned formal validation in Session 2.
- **Read-only, REST**: `GET` search + `GET` read; no writes to the FHIR server in Rung 1.
- Pagination via the standard `link[relation="next"]` URL.

## Auth posture (Rung 1)
- **None.** Default HAPI is open. Justification: faking auth on an open server teaches the wrong handshake. Real SMART/OAuth2, specifically the **Backend Services** flow (the correct flow for an unattended ops layer), is Rung 2 against the SMART Health IT reference sandbox, then Epic's backend sandbox (Rung 3).

## Resources covered (Rung 1)
| Resource | Used for |
|---|---|
| `Patient` | Identity, demographics, telecom (US Core Patient fields) |
| `Appointment` | Booked future visits; gap detection |
| `Encounter` | Past visits; primary signal for recall scoring |
| `Immunization` | Vaccine-recall windows |

Not yet covered: `Observation`, `Condition`, `MedicationRequest`, `AllergyIntolerance`. Easy adds in later sessions; not needed for the first scoring slice.

## Terminology
- **LOINC** (lab/observation codes; Synthea emits these correctly)
- **SNOMED CT** (clinical findings, conditions)
- **CVX** (vaccine codes, relevant for `Immunization` recall)
- **RxNorm** (meds, for refill cadence later)

Rung 1 preserves codes through the mapping but does not validate them against a terminology service. Terminology validation comes with the US Core pass (Session 2) and aligns with n8n Rule 47 (validation + terminology + observability).

## Mapping (FHIR -> ARFA canonical)
Field names match the `manual-csv` canonical schema so AOL modules don't care which connector produced the record.

| FHIR path | ARFA canonical |
|---|---|
| `Patient.id` | `source_emr_id` |
| `Patient.name[0]` (given + family) | `name_display` |
| `Patient.birthDate` | `dob_hash` (SHA-256/16, per MASTER_PRD §6) |
| `Patient.telecom[system=phone]` | `phone` |
| `Patient.gender` | `gender` |
| `Appointment.start` | `scheduled_at` |
| `Appointment.status` | `status` |
| `Appointment.participant[actor=Patient/*]` | `patient_key` |
| `Encounter.subject` (Patient ref) | `patient_key` |
| `Encounter.period.start` | `treatment_at` |
| `Encounter.type[0].coding[0]` | `treatment_type` |
| `Immunization.patient` | `patient_key` |
| `Immunization.vaccineCode.coding[0]` | `vaccine` |
| `Immunization.occurrenceDateTime` | `occurrence` |

## Why Synthea + HAPI (and not Epic sandbox first)
- **Zero PHI:** every artifact is public-safe.
- **Synthea = real FHIR R4** with real codes; the connector ports verbatim to a production endpoint.
- **HAPI is under our control:** no vendor gate, no rate limits, no app review.
- **Epic sandbox** needs app registration + key upload + Epic-specific config (Rung 2/3). Doing Epic first conflates standards skill with vendor-onboarding gates and invites the "we integrate with Epic" overclaim.

## Cross-references
- HL7 FHIR R4 spec: <https://hl7.org/fhir/R4/>
- US Core 6.1.0: <https://hl7.org/fhir/us/core/STU6.1/>
- Synthea: <https://github.com/synthetichealth/synthea>
- HAPI FHIR: <https://hapifhir.io/>
- ARFA `../CONNECTOR_INTERFACE.md`
- ARFA n8n prod patterns Rule 42 (FHIR hardening), Rule 45 (Subscriptions), Rule 47 (validation + terminology + observability)
