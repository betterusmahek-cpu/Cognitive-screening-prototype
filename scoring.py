"""
Deterministic domain scoring + interpretable rule-based classifier.

Design principle (see project spec, section 5): we never sum all 30 items
into one score. We first collapse answers into ten domain-level features,
then combine *those* into per-category evidence scores, then apply
explicit guardrails to choose a final label. Every number here is
reproducible from the domain scores alone -- nothing is hidden in a
trained model, so it stays fully explainable for a prototype.

Nothing in this module is clinically calibrated. Weights and thresholds
are prototype defaults meant to be revisited once reference-labeled data
exists (see spec section 16).
"""

from .questions_data import DOMAIN_QUESTIONS, DOMAIN_IDS, QUESTION_IDS, DISCLAIMER

REQUIRED_FEATURE_KEYS = tuple(DOMAIN_IDS)


class ValidationError(ValueError):
    """Raised when participant answers fail input validation."""


def validate_answers(answers):
    """
    answers: dict-like mapping question id (str or int) -> int 0-4.
    Raises ValidationError with a participant-safe message on any problem.
    Returns a normalized dict[int, int].
    """
    if not isinstance(answers, dict):
        raise ValidationError("answers must be an object mapping question id to a numeric response")

    normalized = {}
    for qid in QUESTION_IDS:
        key_candidates = (str(qid), qid)
        raw = None
        found = False
        for k in key_candidates:
            if k in answers:
                raw = answers[k]
                found = True
                break
        if not found:
            raise ValidationError(f"missing response for question {qid}")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValidationError(f"response for question {qid} must be an integer 0-4")
        if value < 0 or value > 4:
            raise ValidationError(f"response for question {qid} must be between 0 and 4")
        normalized[qid] = value

    extra = set()
    for k in answers.keys():
        try:
            ik = int(k)
        except (TypeError, ValueError):
            extra.add(k)
            continue
        if ik not in QUESTION_IDS:
            extra.add(k)
    if extra:
        raise ValidationError(f"unrecognized question id(s) in answers: {sorted(str(x) for x in extra)}")

    return normalized


def compute_domain_scores(answers):
    """
    answers: dict[int, int] (validated, 0-4) as returned by validate_answers.
    Returns dict[str, float] of the ten domain-level features, each 0-4,
    rounded to two decimals.
    """
    domains = {}
    for domain, qids in DOMAIN_QUESTIONS.items():
        vals = [answers[q] for q in qids]
        domains[domain] = round(sum(vals) / len(vals), 2)
    return domains


def validate_domain_features(features):
    """
    Validate a features dict (e.g. returned by the LLM extractor) has
    exactly the required keys with numeric values in [0, 4].
    Raises ValidationError on any problem. Returns a normalized dict.
    """
    if not isinstance(features, dict):
        raise ValidationError("features must be an object")

    missing = [k for k in REQUIRED_FEATURE_KEYS if k not in features]
    if missing:
        raise ValidationError(f"missing feature keys: {missing}")

    extra = [k for k in features if k not in REQUIRED_FEATURE_KEYS]
    if extra:
        raise ValidationError(f"unexpected feature keys: {extra}")

    normalized = {}
    for k in REQUIRED_FEATURE_KEYS:
        try:
            v = float(features[k])
        except (TypeError, ValueError):
            raise ValidationError(f"feature '{k}' must be numeric")
        if v < 0 or v > 4:
            raise ValidationError(f"feature '{k}' must be between 0 and 4")
        normalized[k] = round(v, 2)
    return normalized


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

# Minimum top evidence score required to assign any category rather than
# "Other / Indeterminate". Evidence scores are on a roughly 0-4 scale.
MIN_EVIDENCE_THRESHOLD = 1.3

# If the top two evidence scores are within this margin of each other, the
# pattern is treated as mixed/overlapping rather than clearly one category.
AMBIGUITY_MARGIN = 0.35

# ADHD guardrail: developmental history is part of the ADHD construct as
# specified (persistent, childhood-onset difficulties). Without at least
# mild endorsement here, we don't award the ADHD label even if attention
# items are elevated, and fall back to Indeterminate instead.
ADHD_HISTORY_FLOOR = 1.0

# Dementia vs MCI differentiator: functional impairment is the key
# distinguishing feature per the project spec (section 4C).
DEMENTIA_FUNCTIONAL_FLOOR = 2.0


_HEALTHY_INPUT_DOMAINS = (
    "attention",
    "hyperactivity",
    "impulsivity",
    "memory",
    "executive",
    "language",
    "orientation",
    "cognitive_decline",
    "functional_impairment",
)


def _evidence_scores(d):
    """
    d: domain feature dict (0-4 each). Returns raw (unnormalized) evidence
    scores for the four named categories. Weights are simple, documented,
    prototype defaults -- not fit to data.
    """
    adhd = (
        0.35 * d["attention"]
        + 0.20 * d["hyperactivity"]
        + 0.20 * d["impulsivity"]
        + 0.25 * d["childhood_history"]
    )

    # MCI evidence is driven by cognitive signal (memory/executive/decline);
    # preserved functional independence is a bonus multiplier on that
    # signal, not a standalone source of evidence -- otherwise a
    # perfectly healthy respondent (low functional impairment, zero
    # cognitive signal) would still accrue nonzero "MCI evidence".
    mci_cognitive_signal = (
        0.35 * d["memory"] + 0.25 * d["executive"] + 0.30 * d["cognitive_decline"]
    )
    functional_preserved_frac = max(0.0, 4 - d["functional_impairment"]) / 4
    mci = mci_cognitive_signal * (0.7 + 0.3 * functional_preserved_frac)

    dementia = (
        0.25 * d["memory"]
        + 0.15 * d["executive"]
        + 0.15 * d["orientation"]
        + 0.15 * d["language"]
        + 0.30 * d["functional_impairment"]
    )

    # "Likely Healthy" evidence should collapse if *any* domain is
    # elevated, not just when the average across domains is elevated --
    # otherwise a sharply elevated single domain (e.g. pure ADHD-pattern
    # attention/hyperactivity/impulsivity) gets diluted by five unrelated
    # domains sitting at zero and wrongly ties with the true category.
    # We blend the mean (overall picture) with the max (worst single
    # signal), weighted toward the max.
    values = [d[k] for k in _HEALTHY_INPUT_DOMAINS]
    mean_impairment = sum(values) / len(values)
    max_impairment = max(values)
    impairment_measure = 0.35 * mean_impairment + 0.65 * max_impairment
    healthy = max(0.0, 4 - impairment_measure)

    return {
        "Probable ADHD": round(adhd, 2),
        "Probable MCI": round(mci, 2),
        "Probable Dementia": round(dementia, 2),
        "Likely Healthy": round(healthy, 2),
    }


def _top_contributing_domains(d, label, n=3):
    weights_by_label = {
        "Probable ADHD": {
            "attention": 0.35,
            "hyperactivity": 0.20,
            "impulsivity": 0.20,
            "childhood_history": 0.25,
        },
        "Probable MCI": {
            "memory": 0.35,
            "executive": 0.25,
            "cognitive_decline": 0.30,
        },
        "Probable Dementia": {
            "memory": 0.25,
            "executive": 0.15,
            "orientation": 0.15,
            "language": 0.15,
            "functional_impairment": 0.30,
        },
        "Likely Healthy": {},
    }
    weights = weights_by_label.get(label, {})
    contributions = sorted(
        ((k, d[k] * w) for k, w in weights.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return [k for k, _ in contributions[:n] if d[k] > 0.5]


_RATIONALE_TEMPLATES = {
    "Probable ADHD": (
        "The response pattern shows elevated attention-related difficulties "
        "and a developmental history of similar difficulties, without a "
        "strong progressive cognitive-decline pattern."
    ),
    "Probable MCI": (
        "The response pattern contains memory and cognitive-decline signals "
        "while reported functional independence remains relatively preserved."
    ),
    "Probable Dementia": (
        "The response pattern shows cognitive difficulties across multiple "
        "domains together with meaningful impairment in independent daily "
        "functioning."
    ),
    "Likely Healthy": (
        "The response pattern shows low impairment across the measured "
        "attention and cognitive domains, with preserved daily functioning "
        "and no strong persistent symptom pattern."
    ),
    "Other / Indeterminate": (
        "The response pattern does not clearly match a single screening "
        "category -- evidence is mixed, overlapping across categories, or "
        "too limited to support a specific classification."
    ),
}


def classify(domains):
    """
    domains: dict[str, float] with the ten domain feature keys (0-4 each).
    Returns the full classification result dict described in the spec.
    """
    for k in REQUIRED_FEATURE_KEYS:
        if k not in domains:
            raise ValidationError(f"missing domain feature: {k}")

    scores = _evidence_scores(domains)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_score = ranked[0]
    second_label, second_score = ranked[1]

    label = None
    if top_score < MIN_EVIDENCE_THRESHOLD:
        label = "Other / Indeterminate"
    elif (top_score - second_score) < AMBIGUITY_MARGIN:
        label = "Other / Indeterminate"
    elif top_label == "Probable ADHD" and domains["childhood_history"] < ADHD_HISTORY_FLOOR:
        label = "Other / Indeterminate"
    elif top_label == "Probable MCI" and domains["functional_impairment"] >= DEMENTIA_FUNCTIONAL_FLOOR:
        # Substantial functional impairment pushes this toward the
        # dementia prototype rather than MCI, per the spec's stated
        # differentiator, if dementia evidence is at all competitive.
        if scores["Probable Dementia"] >= scores["Probable MCI"] - AMBIGUITY_MARGIN:
            label = "Probable Dementia"
        else:
            label = top_label
    else:
        label = top_label

    if label == "Other / Indeterminate":
        confidence = round(max(0.15, 0.5 - (MIN_EVIDENCE_THRESHOLD - top_score if top_score < MIN_EVIDENCE_THRESHOLD else (top_score - second_score))), 2)
        confidence = min(confidence, 0.45)
        rationale = _RATIONALE_TEMPLATES["Other / Indeterminate"]
        contributing = []
    else:
        spread = max(0.01, top_score - second_score)
        confidence = round(min(0.95, 0.45 + spread * 0.35 + (top_score / 4) * 0.2), 2)
        rationale = _RATIONALE_TEMPLATES[label]
        contributing = _top_contributing_domains(domains, label)

    return {
        "label": label,
        "confidence": confidence,
        "scores": scores,
        "domains": domains,
        "contributing_domains": contributing,
        "rationale": rationale,
        "disclaimer": DISCLAIMER,
    }
