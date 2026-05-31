window.FHIR_FOLLOWUP = {
  "source": "FHIR R4 via REST (https://hapi.fhir.org/baseR4)",
  "scoped_by_tag": "http://arfa-demo.test/run|aol-demo",
  "generated_at": "2026-05-30T23:24:00.095277+00:00",
  "recall_window_days": 365,
  "counts": {
    "needs_call": 3,
    "soft_touch": 2,
    "no_action": 3
  },
  "items": [
    {
      "patient_name": "Robert Lee",
      "patient_id": "135198621",
      "bucket": "Needs call this week",
      "days_since_last_encounter": 500,
      "personal_cadence_days": null,
      "score": 0.811,
      "explanation": "last visit 500d ago, vs 365d recall window"
    },
    {
      "patient_name": "Maria Gonzalez",
      "patient_id": "135198607",
      "bucket": "Needs call this week",
      "days_since_last_encounter": 400,
      "personal_cadence_days": 200,
      "score": 0.729,
      "explanation": "last visit 400d ago, vs 365d recall window"
    },
    {
      "patient_name": "David Nguyen",
      "patient_id": "135198626",
      "bucket": "Needs call this week",
      "days_since_last_encounter": 380,
      "personal_cadence_days": 20,
      "score": 0.712,
      "explanation": "last visit 380d ago, vs 365d recall window"
    },
    {
      "patient_name": "James Carter",
      "patient_id": "135198611",
      "bucket": "Soft touch",
      "days_since_last_encounter": 90,
      "personal_cadence_days": 30,
      "score": 0.69,
      "explanation": "last visit 90d ago, vs 30d personal cadence (drift)"
    },
    {
      "patient_name": "Frank Miller",
      "patient_id": "135198632",
      "bucket": "Soft touch",
      "days_since_last_encounter": 100,
      "personal_cadence_days": 50,
      "score": 0.6,
      "explanation": "last visit 100d ago, vs 50d personal cadence (drift)"
    },
    {
      "patient_name": "Aisha Khan",
      "patient_id": "135198617",
      "bucket": "No action",
      "days_since_last_encounter": 15,
      "personal_cadence_days": 22,
      "score": 0.1,
      "explanation": "within cadence (last 15d ago, cadence 22d)"
    },
    {
      "patient_name": "Linda Park",
      "patient_id": "135198623",
      "bucket": "No action",
      "days_since_last_encounter": 60,
      "personal_cadence_days": 60,
      "score": 0.1,
      "explanation": "within cadence (last 60d ago, cadence 60d)"
    },
    {
      "patient_name": "Emily Davis",
      "patient_id": "135198629",
      "bucket": "No action",
      "days_since_last_encounter": 25,
      "personal_cadence_days": 25,
      "score": 0.1,
      "explanation": "within cadence (last 25d ago, cadence 25d)"
    }
  ]
};
