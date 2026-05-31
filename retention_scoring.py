"""
ARFA AOL — Retention / recall scoring (Rung 1, FHIR demo).

Given canonical patients + encounters (from `connector.py`), return a sorted
follow-up-priority list. Mirrors the AOL retention-engine intent: surface
the operations layer the EHR does not show.

Rung 1 scoring is deliberately simple and reproducible:
- `days_since_last_encounter` is the primary signal.
- `personal_cadence_days` is the median gap between this patient's visits.
- Three buckets:
    * "Needs call this week"  - past the practice recall window.
    * "Soft touch"            - past 1.5x personal cadence but inside the window.
    * "No action"             - within cadence.

Per-condition recall (diabetes 90d etc.) and US Core profile extensions come
in Session 2/3 once Condition is loaded.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

DEFAULT_RECALL_WINDOW_DAYS = 365  # primary-care default; aesthetic module overrides


@dataclass
class FollowUpItem:
    patient_id: str
    patient_name: str
    days_since_last_encounter: Optional[int]
    personal_cadence_days: Optional[int]
    bucket: str        # "Needs call this week" | "Soft touch" | "No action"
    score: float       # 0..1 priority
    explanation: str


def score_patients(
    patients: Iterable[dict],
    encounters_by_patient: dict[str, list[dict]],
    recall_window_days: int = DEFAULT_RECALL_WINDOW_DAYS,
    anchor: Optional[datetime] = None,
) -> list[FollowUpItem]:
    """Return FollowUpItem list sorted by descending priority score."""
    anchor = anchor or datetime.now(timezone.utc)
    out: list[FollowUpItem] = []
    for p in patients:
        pid = p.get("source_emr_id") or ""
        encs = sorted(encounters_by_patient.get(pid, []), key=_enc_dt_key)
        last = encs[-1] if encs else None
        days_since = _days_between(_enc_dt(last), anchor) if last else None
        cadence = _personal_cadence_days(encs)
        bucket, score, why = _bucket(days_since, cadence, recall_window_days)
        out.append(FollowUpItem(
            patient_id=pid,
            patient_name=p.get("name_display") or "",
            days_since_last_encounter=days_since,
            personal_cadence_days=cadence,
            bucket=bucket,
            score=score,
            explanation=why,
        ))
    out.sort(key=lambda i: i.score, reverse=True)
    return out


# ------------------------- internals -------------------------

def _enc_dt(enc: Optional[dict]) -> Optional[datetime]:
    if not enc:
        return None
    raw = enc.get("treatment_at") or ""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _enc_dt_key(enc: dict) -> datetime:
    # Sort key with epoch fallback so encounters without a date land at the start.
    return _enc_dt(enc) or datetime.fromtimestamp(0, tz=timezone.utc)


def _days_between(a: Optional[datetime], b: datetime) -> Optional[int]:
    if a is None:
        return None
    # Normalise to UTC if either is naive.
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return max(0, (b - a).days)


def _personal_cadence_days(encs: list[dict]) -> Optional[int]:
    """Median day-gap between this patient's encounters. None if fewer than 2."""
    dts = [d for d in (_enc_dt(e) for e in encs) if d is not None]
    if len(dts) < 2:
        return None
    gaps = [(b - a).days for a, b in zip(dts, dts[1:]) if (b - a).days > 0]
    if not gaps:
        return None
    return int(statistics.median(gaps))


def _bucket(days_since: Optional[int], cadence: Optional[int], recall_window: int):
    if days_since is None:
        return "No action", 0.10, "no encounters on file; cannot score yet"
    if days_since >= recall_window:
        over = days_since - recall_window
        score = min(1.0, 0.70 + (over / recall_window) * 0.30)
        return "Needs call this week", round(score, 3), (
            f"last visit {days_since}d ago, vs {recall_window}d recall window"
        )
    if cadence is not None and days_since >= int(1.5 * cadence):
        score = min(0.69, 0.40 + (days_since - cadence) / max(cadence, 1) * 0.20)
        return "Soft touch", round(score, 3), (
            f"last visit {days_since}d ago, vs {cadence}d personal cadence (drift)"
        )
    return "No action", 0.10, (
        f"within cadence (last {days_since}d ago, cadence "
        f"{cadence if cadence is not None else 'n/a'}d)"
    )
