"""GLiNER2 zero-shot extractor — Auto AND Health claims.

Strategy (bi-encoder specific):
  knowledgator/gliner-bi-large-v2.0 uses embedding similarity, so label
  phrases must be SHORT and CONCRETE — the model scores cosine similarity
  between the label embedding and each token span.  Long descriptive labels
  score near-zero because they dilute the embedding signal.

  We therefore:
    1. Run GLiNER with short labels at a low threshold (0.22).
    2. Run the regex/heuristic extractor IN PARALLEL as an additive layer.
    3. Merge both results — keep the higher confidence per pillar.

  This gives us:
    - GLiNER for fuzzy/semantic matching (Dr. Schmidt → provider_name)
    - Regex for high-precision structural patterns (14:30, K-AB 1234, A4)
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Callable, Awaitable
from dataclasses import dataclass
from typing import Any

# ── GLiNER label vocabulary (SHORT is better for bi-encoder) ─────────────────
# Rule: every canonical ID MUST match a key in ClaimState.PILLARS,
#       gliner2_service.HUMAN_TO_ID, and ClaimProgress.jsx PILLARS list.

HUMAN_TO_ID: dict[str, str] = {
    # Universal
    "claim type":               "claim_type",
    "auto or health claim":     "claim_type",
    "date":                     "incident_datetime",
    "time":                     "incident_datetime",
    "location":                 "incident_location",
    "address":                  "incident_location",
    "injury":                   "injuries_or_symptoms",
    "symptom":                  "injuries_or_symptoms",
    "pain":                     "injuries_or_symptoms",
    "what happened":            "how_it_happened",
    "incident description":     "how_it_happened",

    # Health-specific
    "medical treatment":        "treatment_received",
    "doctor":                   "provider_name",
    "hospital":                 "provider_name",
    "clinic":                   "provider_name",

    # Auto-specific
    "vehicle drivable":         "vehicle_drivable",
    "car drivable":             "vehicle_drivable",
    "license plate":            "other_party_plate",
    "other party insurer":      "other_party_insurer",
    "fault":                    "fault_admission",
    "witness":                  "witnesses",
    "repair shop":              "settlement_preference",
    "reimbursement preference": "settlement_preference",
    "police":                   "police_or_ambulance",
    "ambulance":                "police_or_ambulance",
    "police case number":       "police_case_number",
}

FRAUD_HUMAN_TO_ID: dict[str, str] = {
    "delayed reporting":               "delayed_reporting",
    "known relationship other party":  "known_to_other_party",
    "vehicle listed for sale":         "vehicle_listed_for_sale",
    "prior similar incident":          "prior_similar_incident",
    "timeline inconsistency":          "timeline_inconsistency",
}

FRAUD_IDS = set(FRAUD_HUMAN_TO_ID.values())

# Canonical label-ID vocabularies, derived from the maps above so they can never
# drift out of sync with them. `extraction.gemini_extractor` imports these as the
# default (no-domain) target set; each ID matches a ClaimState.PILLARS key per the
# invariant noted above.
CLAIM_LABELS: list[str] = sorted(set(HUMAN_TO_ID.values()))
FRAUD_LABELS: list[str] = sorted(FRAUD_IDS)

_MODEL_CANDIDATES = [
    "fastino/gliner2-base-v1",
    "knowledgator/gliner-bi-large-v2.0",
    "knowledgator/gliner-multitask-large-v0.5",
]


@dataclass
class Extraction:
    label: str
    text: str
    score: float


def _merge(base: dict[str, Extraction], overlay: dict[str, Extraction]) -> dict[str, Extraction]:
    """Merge two extraction dicts, keeping the higher-confidence value per key."""
    merged = dict(base)
    for k, v in overlay.items():
        if k not in merged or merged[k].score < v.score:
            merged[k] = v
    return merged


class ExtractionService:
    """Wraps GLiNER2 + regex fallback with merge strategy."""

    def __init__(self, model_name: str | None = None, threshold: float = 0.22) -> None:
        self.threshold = threshold
        self.model_name: str | None = None
        self._model: Any = None
        self._mode: str = "stub"

        try:
            from gliner import GLiNER  # type: ignore
            for candidate in ([model_name] if model_name else _MODEL_CANDIDATES):
                if not candidate:
                    continue
                try:
                    self._model = GLiNER.from_pretrained(candidate)
                    self.model_name = candidate
                    self._mode = "gliner"
                    break
                except Exception:
                    continue
        except Exception:
            self._model = None

    @property
    def mode(self) -> str:
        return self._mode

    def extract(self, text: str) -> dict[str, Any]:
        """Run GLiNER + regex, merge results, return unified pillar/fraud dict."""
        t0 = time.perf_counter()
        gliner_pillars:  dict[str, Extraction] = {}
        gliner_fraud:    dict[str, Extraction] = {}

        # ── 1. GLiNER semantic pass ───────────────────────────────────────────
        if self._mode == "gliner" and self._model is not None:
            all_labels = list(HUMAN_TO_ID.keys()) + list(FRAUD_HUMAN_TO_ID.keys())
            try:
                ents = self._model.predict_entities(text, all_labels, threshold=self.threshold)
                for e in ents:
                    human = e["label"]
                    lab = HUMAN_TO_ID.get(human) or FRAUD_HUMAN_TO_ID.get(human)
                    if not lab:
                        continue
                    ex = Extraction(label=lab, text=e["text"], score=float(e.get("score", 0.0)))
                    bucket = gliner_fraud if lab in FRAUD_IDS else gliner_pillars
                    if lab not in bucket or bucket[lab].score < ex.score:
                        bucket[lab] = ex
            except Exception as gliner_err:
                print(f"  [gliner] predict error: {gliner_err}")

        # ── 2. Regex structural pass (always runs — additive, not fallback) ──
        regex_pillars, regex_fraud = _regex_extract(text)

        # ── 3. Merge: higher confidence wins per label ────────────────────────
        final_pillars = _merge(gliner_pillars, regex_pillars)
        final_fraud   = _merge(gliner_fraud,   regex_fraud)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "pillars":    {k: v.__dict__ for k, v in final_pillars.items()},
            "fraud":      {k: v.__dict__ for k, v in final_fraud.items()},
            "elapsed_ms": round(elapsed_ms, 2),
            "mode":       self._mode,
            "model":      self.model_name,
            "emotional_state": _detect_emotion(text),
        }


# ── Emotion detection ─────────────────────────────────────────────────────────
_RE_DISTRESSED = re.compile(r"\b(pain|hurt|emergency|scared|help|please|crying|ambulance|bleeding|broken|dying|shaking|frightened|chest\s+pain|headache|fracture|surgery|terrible|suffering|agonizing|painful|sick|hurt|injured)\b", re.I)
_RE_NOISY      = re.compile(r"\b(can't\s+hear|loud|background|noise|static|interference|wind|highway|traffic|bad\s+connection|breaking\s+up|echo)\b", re.I)

def _detect_emotion(text: str) -> str:
    lower = text.lower()
    if _RE_DISTRESSED.search(lower): return "distressed"
    if _RE_NOISY.search(lower):      return "noisy"
    return "calm"


# ── Async streaming wrapper ───────────────────────────────────────────────────
async def run_async_extractor(
    transcript_stream: AsyncIterator[str],
    on_update: Callable[[dict[str, Any]], Awaitable[None]],
    chunk_words: int = 20,
    service: ExtractionService | None = None,
) -> None:
    svc = service or ExtractionService()
    buffer: list[str] = []
    async for piece in transcript_stream:
        buffer.append(piece)
        words = " ".join(buffer).split()
        if len(words) < chunk_words:
            continue
        chunk = " ".join(words[-chunk_words * 2:])
        result = await asyncio.to_thread(svc.extract, chunk)
        if result["pillars"] or result["fraud"]:
            await on_update(result)
        buffer = [chunk]


# ── Regex / heuristic extractor ───────────────────────────────────────────────
# These fire on high-precision structural patterns that GLiNER often misses:
# timestamps, license plates, A-road codes, medical keywords, etc.
_RE_DATE        = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{2,4}|today|yesterday|last\s+\w+day)\b", re.I)
_RE_TIME        = re.compile(r"\b(\d{1,2}:\d{2}(?:\s*[ap]m)?)\b", re.I)
_RE_LOCATION    = re.compile(r"\b(A\d{1,3}|B\d{1,3}|Autobahn|[A-Z][a-z]+(straße|strasse|street|road|avenue|ave|blvd|platz|gasse))\b", re.I)
_RE_CITY        = re.compile(r"\b(Berlin|München|Munich|Hamburg|Frankfurt|Köln|Cologne|Stuttgart|Düsseldorf|Leipzig|Dortmund|Essen|Bremen|Dresden|Hannover)\b", re.I)
_RE_HOSPITAL    = re.compile(r"\b(hospital|clinic|medical\s+cent(?:er|re)|Krankenhaus|Klinik|ER|emergency\s+room|Notaufnahme)\b", re.I)
_RE_DOCTOR      = re.compile(r"\bDr\.?\s+[A-Z][a-z]+\b|\b(doctor|physician|specialist|surgeon|GP|general\s+practitioner)\b", re.I)
_RE_INJURY      = re.compile(r"\b(whiplash|fracture|broken|bleeding|concussion|bruise|burn|sprain|chest\s+pain|headache|fever|nausea|dizziness|surgery|ambulance|hurt|pain|injured|Schmerz|verletzt|Kopfschmerzen|Fieber)\b", re.I)
_RE_TREATMENT   = re.compile(r"\b(surgery|operation|stitches|X-?ray|MRI|CT\s+scan|medication|prescription|physiotherapy|rehab|treatment|Behandlung|Operation|Medikament)\b", re.I)
_RE_PLATE       = re.compile(r"\b([A-ZÄÖÜ]{1,3}[-\s][A-Z]{1,2}\s?\d{1,4})\b")
_RE_DRIVABLE_NO = re.compile(r"\b(not\s+drivable|cannot\s+drive|totaled?|write[-\s]off|kann\s+nicht\s+fahren|Totalschaden)\b", re.I)
_RE_DRIVABLE_OK = re.compile(r"\b(still\s+drivable|still\s+drives?|drove\s+home|fahrtüchtig)\b", re.I)
_RE_POLICE      = re.compile(r"\b(police|Polizei|cops|officers?)\b", re.I)
_RE_AMBULANCE   = re.compile(r"\b(ambulance|paramedic|Rettungswagen|Notarzt)\b", re.I)
_RE_POLICE_NUM  = re.compile(r"\b(?:case|reference|report)\s*(?:number|no\.?|#)?\s*[:#]?\s*(\w{4,})\b", re.I)
_RE_FAULT       = re.compile(r"\b(my fault|their fault|I caused|they caused|ran the red|Schuld|verschuldet)\b", re.I)
_RE_WITNESS     = re.compile(r"\b(witness(?:es)?|bystander|passerby|Zeuge)\b", re.I)
_RE_CLAIM_AUTO  = re.compile(r"\b(car|auto|vehicle|automobile|accident|crash|collision|KFZ|Unfall|Fahrzeug|motor)\b", re.I)
_RE_CLAIM_HEALTH= re.compile(r"\b(health|medical|illness|sick|Krankenkasse|Krankenversicherung|Gesundheit|fracture|surgery|doctor|hospital|clinic|injury|injured)\b", re.I)
_RE_DELAY       = re.compile(r"\b(\d+)\s+(weeks?|months?|days?)\s+ago\b", re.I)
_RE_SETTLEMENT  = re.compile(r"\b(repair\s+shop|body\s+shop|reimburs|direct\s+payment|Werkstatt|Erstattung)\b", re.I)
_RE_HAPPENED    = re.compile(r"\b(crashed|hit|collided|fell|slipped|tripped|broke|started\s+to\s+pain|attack|seizure|emergency|accident|incident|Unfall|Sturz|Schmerzen)\b", re.I)
_RE_REL_TIME    = re.compile(r"\b(just\s+now|a\s+moment\s+ago|an\s+hour\s+ago|\d+\s+minutes\s+ago|this\s+morning|last\s+night|today|yesterday)\b", re.I)


def _regex_extract(text: str) -> tuple[dict[str, Extraction], dict[str, Extraction]]:
    pillars: dict[str, Extraction] = {}
    fraud:   dict[str, Extraction] = {}

    def add(d: dict, key: str, val: str, score: float) -> None:
        if key not in d or d[key].score < score:
            d[key] = Extraction(key, val, score)

    # claim_type — detect early so downstream can branch
    if _RE_CLAIM_HEALTH.search(text):
        add(pillars, "claim_type", "health", 0.85)
    elif _RE_CLAIM_AUTO.search(text):
        add(pillars, "claim_type", "auto", 0.65)

    # incident_datetime
    for m in _RE_DATE.finditer(text):
        add(pillars, "incident_datetime", m.group(1), 0.72)
    for m in _RE_TIME.finditer(text):
        add(pillars, "incident_datetime", m.group(1), 0.68)

    # incident_location — roads, cities, hospitals
    for m in _RE_LOCATION.finditer(text):
        add(pillars, "incident_location", m.group(0), 0.75)
    for m in _RE_CITY.finditer(text):
        add(pillars, "incident_location", m.group(0), 0.60)
    for m in _RE_HOSPITAL.finditer(text):
        add(pillars, "incident_location", m.group(0), 0.65)

    # injuries_or_symptoms
    for m in _RE_INJURY.finditer(text):
        add(pillars, "injuries_or_symptoms", m.group(0), 0.78)

    # how_it_happened
    for m in _RE_HAPPENED.finditer(text):
        add(pillars, "how_it_happened", m.group(0), 0.65)

    # more flexible relative time
    for m in _RE_REL_TIME.finditer(text):
        add(pillars, "incident_datetime", m.group(0), 0.60)

    # treatment_received
    for m in _RE_TREATMENT.finditer(text):
        add(pillars, "treatment_received", m.group(0), 0.72)

    # provider_name (doctor / hospital)
    for m in _RE_DOCTOR.finditer(text):
        add(pillars, "provider_name", m.group(0), 0.80)
    for m in _RE_HOSPITAL.finditer(text):
        add(pillars, "provider_name", m.group(0), 0.68)

    # vehicle-specific
    for m in _RE_PLATE.finditer(text):
        add(pillars, "other_party_plate", m.group(1), 0.85)
    for m in _RE_DRIVABLE_NO.finditer(text):
        add(pillars, "vehicle_drivable", "no", 0.80)
    for m in _RE_DRIVABLE_OK.finditer(text):
        add(pillars, "vehicle_drivable", "yes", 0.75)
    for m in _RE_SETTLEMENT.finditer(text):
        add(pillars, "settlement_preference", m.group(0), 0.65)

    # police / ambulance
    if _RE_POLICE.search(text):
        add(pillars, "police_or_ambulance", "police", 0.78)
    if _RE_AMBULANCE.search(text):
        add(pillars, "police_or_ambulance", "ambulance", 0.80)
    for m in _RE_POLICE_NUM.finditer(text):
        add(pillars, "police_case_number", m.group(1), 0.82)

    # fault / witness
    for m in _RE_FAULT.finditer(text):
        add(pillars, "fault_admission", m.group(0), 0.78)
    for m in _RE_WITNESS.finditer(text):
        add(pillars, "witnesses", m.group(0), 0.65)

    # fraud signals
    for m in _RE_DELAY.finditer(text):
        add(fraud, "delayed_reporting", m.group(0), 0.70)

    return pillars, fraud


# ── self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Run: .venv/bin/python tests/test_extraction.py
    pass
