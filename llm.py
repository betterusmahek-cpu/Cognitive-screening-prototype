"""
Optional LLM-assisted feature extraction.

The LLM is never asked to diagnose the participant. Its only job is to
convert the questionnaire responses into the same structured domain
feature vector the deterministic scorer produces, returned as strict
JSON. The classifier downstream treats this exactly like the
deterministic domain scores -- it does not know or care where they came
from.

If the LLM is unavailable, times out, returns malformed JSON, or returns
a schema that doesn't validate, the caller (api/screen.py) must fall back
to deterministic scoring. This module never raises to the participant;
it raises internal exceptions that the caller catches.
"""

import json
import os
import urllib.request
import urllib.error

from .questions_data import QUESTIONS, DOMAIN_IDS
from .scoring import validate_domain_features, ValidationError

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
REQUEST_TIMEOUT_SECONDS = 12

SYSTEM_PROMPT = (
    "You are a research data extraction component. Convert the "
    "participant's questionnaire responses into structured cognitive and "
    "behavioral features. Do not diagnose the participant. Return only "
    "strict JSON matching the schema you are given, with no additional "
    "fields, commentary, or markdown formatting."
)

_SCHEMA_KEYS = tuple(DOMAIN_IDS)


class LLMExtractionError(Exception):
    """Raised on any failure to obtain a valid feature vector from the LLM."""


def _build_user_prompt(answers):
    lines = [
        "Participant questionnaire responses (question id: response value, "
        "0-4 scale, higher = more frequent/severe):",
        "",
    ]
    by_id = {q["id"]: q for q in QUESTIONS}
    for qid in sorted(answers.keys()):
        q = by_id[qid]
        lines.append(f'Q{qid} [{q["domain"]}]: "{q["text"]}" -> {answers[qid]}')

    lines.append("")
    lines.append(
        "Aggregate these into the following domain features, each a "
        "number from 0 to 4 (can include one decimal place), representing "
        "the overall level of difficulty/decline in that domain based on "
        "the responses above:"
    )
    lines.append(json.dumps({k: "0-4" for k in _SCHEMA_KEYS}, indent=2))
    lines.append(
        "\nReturn ONLY a JSON object with exactly these keys and numeric "
        "values in [0, 4]. Do not add any other keys."
    )
    return "\n".join(lines)


def llm_extract_domains(answers, api_key=None, model=None):
    """
    answers: dict[int, int], validated 0-4 responses.
    Returns a validated dict[str, float] of domain features on success.
    Raises LLMExtractionError on any failure -- caller must catch this
    and fall back to deterministic scoring.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("no OPENAI_API_KEY configured")

    model = model or DEFAULT_MODEL

    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(answers)},
        ],
    }

    req = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMExtractionError(f"OpenAI API HTTP error: {e.code}") from e
    except urllib.error.URLError as e:
        raise LLMExtractionError(f"OpenAI API unreachable or timed out: {e}") from e
    except (TimeoutError, OSError) as e:
        raise LLMExtractionError(f"OpenAI API timeout: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMExtractionError("unexpected OpenAI API response shape") from e

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as e:
        raise LLMExtractionError("LLM did not return valid JSON") from e

    try:
        validated = validate_domain_features(parsed)
    except ValidationError as e:
        raise LLMExtractionError(f"LLM JSON failed schema validation: {e}") from e

    return validated
