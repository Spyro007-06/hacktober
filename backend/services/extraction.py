"""Complaint extraction: prompt -> provider -> strict validation into the PRD's
`Extraction` model, with exactly one corrective retry (PRD p.5).

The model only extracts facts. Routes are never read from model output
(`Extraction` forbids unknown fields) and are decided in services/routing.py.
"""
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pydantic import ValidationError

from backend.errors import model_invalid_output
from backend.models import ASKABLE_FIELDS, Extraction
from backend.services.llm import ImagePart, LLMProvider

log = logging.getLogger("kural.extraction")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract.txt"
MAX_ATTEMPTS = 2  # first try + exactly one retry

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)

PHOTO_RULE_WITH = (
    "Photos are attached ({n}). photo_findings: short factual descriptions of what the photos "
    "show. photo_matches_claim: true if they are consistent with the problem described, false "
    "if they clearly show something else (explain in photo_mismatch_note), null if unclear."
)
PHOTO_RULE_NONE = (
    "No photo was supplied: photo_findings must be [], photo_matches_claim must be null and "
    "photo_mismatch_note must be null."
)


def build_prompt(text: str, language: str, answers: Mapping[str, str], n_photos: int) -> str:
    schema = json.dumps(Extraction.model_json_schema(), ensure_ascii=False)
    photo_rule = PHOTO_RULE_WITH.format(n=n_photos) if n_photos else PHOTO_RULE_NONE
    answer_lines = "\n".join(f"{k}: {v}" for k, v in answers.items()) or "(none)"
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    for token, value in (("__PHOTO_RULE__", photo_rule), ("__SCHEMA__", schema),
                         ("__LANGUAGE__", "Tamil" if language == "ta" else "English"),
                         ("__COMPLAINT__", text), ("__ANSWERS__", answer_lines)):
        prompt = prompt.replace(token, value)
    return prompt


def parse_extraction(raw: str) -> Extraction:
    """Strict parse. Raises ValueError (bad JSON / not an object) or
    ValidationError (schema violation, unknown field, bad value)."""
    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:  # tolerate one enclosing markdown fence, nothing else
        text = fenced.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("the reply was not valid JSON")
    if not isinstance(obj, dict):
        raise ValueError("the reply was not a JSON object")
    return Extraction.model_validate(obj)


def describe_error(exc: Exception) -> str:
    """Field paths and messages only: never the model's output or any input
    values, so no personal data is echoed back to the model."""
    if isinstance(exc, ValidationError):
        items = [f"{'.'.join(str(p) for p in e['loc']) or 'reply'}: {e['msg']}" for e in exc.errors()]
        return "; ".join(items)[:600]
    return str(exc)[:200]


def _squash(value: str) -> str:
    """Case/punctuation/whitespace-insensitive form, for checking quoted words."""
    # Keep letters, combining marks and digits: Tamil vowel signs are marks, not letters.
    return "".join(c for c in value.casefold() if unicodedata.category(c)[0] in "LMN")


def location_is_grounded(location: Optional[str], text: str, answers: Mapping[str, str]) -> bool:
    """True when the location the model reported appears in the citizen's own words
    (the complaint text or an answer). The prompt asks for the location 'exactly as
    the citizen gave it', so a location that is not there is a guess. Locations drive
    the match with earlier complaints (and so R3), so a guess must not be used."""
    wanted = _squash(location or "")
    if not wanted:
        return False
    return any(wanted in _squash(source) for source in (text, *answers.values()))


def finalize(extraction: Extraction, n_photos: int, answers: Mapping[str, str],
             text: Optional[str] = None) -> Extraction:
    """Deterministic post-processing the model is not trusted with. When `text` is
    given, a location that does not appear in the citizen's words is dropped, so it
    becomes a follow-up question instead of an unsupported fact."""
    update: dict = {}
    if text is not None and not answers.get("location_text") and extraction.location_text \
            and not location_is_grounded(extraction.location_text, text, answers):
        update["location_text"] = None
    # The citizen's own words for the location win over the model's reading.
    loc = ", ".join(v for v in (answers.get("location_text"), answers.get("area")) if v)
    if loc:
        update["location_text"] = loc
    if answers.get("duration"):
        update["duration"] = answers["duration"]
    if n_photos == 0:  # never claim photo evidence that was not supplied
        update.update(photo_findings=[], photo_matches_claim=None, photo_mismatch_note=None)
    merged = extraction.model_copy(update=update)
    missing = [f for f in ASKABLE_FIELDS if not (getattr(merged, f) or "").strip()]
    return merged.model_copy(update={"missing_fields": missing})


async def extract(
    provider: LLMProvider,
    *,
    text: str,
    language: str,
    images: Sequence[ImagePart] = (),
    answers: Optional[Mapping[str, str]] = None,
) -> Extraction:
    """Provider failures (MODEL_TIMEOUT / MODEL_UNAVAILABLE) propagate
    untouched and are never retried or turned into a result."""
    answers = answers or {}
    schema = Extraction.model_json_schema()
    base_prompt = build_prompt(text, language, answers, len(images))
    prompt = base_prompt
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = await provider.generate_json(prompt, images, schema)
        try:
            return finalize(parse_extraction(raw), len(images), answers, text)
        except (ValueError, ValidationError) as exc:
            log.warning("invalid model output attempt=%d/%d error_type=%s",
                        attempt, MAX_ATTEMPTS, type(exc).__name__)
            problem = describe_error(exc)
        prompt = (base_prompt + "\n\nYour previous reply was rejected: " + problem +
                  "\nReply again with ONLY one corrected JSON object that follows the schema exactly.")
    raise model_invalid_output()
