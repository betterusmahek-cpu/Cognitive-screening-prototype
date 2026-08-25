"""
Single source of truth for the questionnaire: item text, domain mapping,
and response scales. Both /api/questions and /api/screen import from here
so the frontend, the scorer, and the (optional) LLM extractor never drift
out of sync with each other.

This is a RESEARCH PROTOTYPE question set. It is not a validated clinical
instrument and must not be described as one.
"""

FREQUENCY_SCALE = [
    {"value": 0, "label": "Never"},
    {"value": 1, "label": "Rarely"},
    {"value": 2, "label": "Sometimes"},
    {"value": 3, "label": "Often"},
    {"value": 4, "label": "Very often"},
]

CHANGE_SCALE = [
    {"value": 0, "label": "No change"},
    {"value": 1, "label": "Slight change"},
    {"value": 2, "label": "Noticeable change"},
    {"value": 3, "label": "Significant change"},
    {"value": 4, "label": "Severe change"},
]

INDEPENDENCE_SCALE = [
    {"value": 0, "label": "Completely independent"},
    {"value": 1, "label": "Independent, but with minor difficulty"},
    {"value": 2, "label": "Occasionally need assistance"},
    {"value": 3, "label": "Frequently need assistance"},
    {"value": 4, "label": "Unable to perform independently"},
]

SCALES = {
    "frequency": FREQUENCY_SCALE,
    "change": CHANGE_SCALE,
    "independence": INDEPENDENCE_SCALE,
}

# domain -> human-readable section title + short description shown in the UI
SECTIONS = [
    {"id": "attention", "title": "Attention & Focus", "range": (1, 7)},
    {"id": "hyperactivity", "title": "Hyperactivity", "range": (8, 9)},
    {"id": "impulsivity", "title": "Impulsivity", "range": (10, 11)},
    {"id": "childhood_history", "title": "Developmental History", "range": (12, 14)},
    {"id": "memory", "title": "Memory", "range": (15, 19)},
    {"id": "executive", "title": "Executive Function", "range": (20, 22)},
    {"id": "language", "title": "Language", "range": (23, 23)},
    {"id": "orientation", "title": "Orientation", "range": (24, 24)},
    {"id": "cognitive_decline", "title": "Cognitive Change", "range": (25, 27)},
    {"id": "functional_impairment", "title": "Daily Functioning", "range": (28, 30)},
]

_QUESTION_TEXT = {
    1: "How often do you have difficulty maintaining attention during a task, lecture, conversation, or activity?",
    2: "How often do you make mistakes because you overlook details or fail to notice important information?",
    3: "How often do you start tasks but have difficulty finishing them?",
    4: "How often do you have difficulty organizing your work, studies, or daily activities?",
    5: "How often do you avoid or delay tasks that require prolonged mental effort?",
    6: "How often are you easily distracted by unrelated sounds, thoughts, notifications, or activities?",
    7: "How often do you forget appointments, deadlines, instructions, or everyday responsibilities?",
    8: "How often do you feel restless when you are expected to remain seated or still?",
    9: "How often do you feel unable to relax without doing something or keeping yourself occupied?",
    10: "How often do you interrupt conversations or answer before another person has finished speaking?",
    11: "How often do you find it difficult to wait for your turn?",
    12: "Did you experience persistent difficulties with attention, organization, or impulsivity during childhood?",
    13: "During childhood or adolescence, did these difficulties interfere with your schoolwork, relationships, or daily activities?",
    14: "Have your attention-related difficulties been present for a long period rather than appearing only recently?",
    15: "How often do you forget information that you learned recently?",
    16: "How often do you forget conversations or events that happened recently?",
    17: "How often do you repeat a question, story, or information because you do not remember having already mentioned it?",
    18: "How often do you have difficulty learning and remembering new information?",
    19: "How often do you forget where you have placed commonly used objects?",
    20: "How often do you have difficulty planning or carrying out a familiar multi-step task?",
    21: "How often do you have difficulty solving a problem that you previously would have handled easily?",
    22: "How often do you lose track of the steps while performing an ordinary task?",
    23: "How often do you have difficulty finding familiar words while speaking or writing?",
    24: "How often do you become confused about dates, times, locations, or where you are going?",
    25: "Compared with your previous level of ability, how much decline have you noticed in your memory or thinking?",
    26: "How much have other people noticed a change in your memory, thinking, or ability to perform familiar tasks?",
    27: "How much has your memory or thinking difficulty progressively increased over time?",
    28: "How much difficulty do you have independently managing finances, payments, or important documents?",
    29: "How much difficulty do you have independently managing medications, appointments, schedules, or important responsibilities?",
    30: "How much difficulty do you have independently managing everyday activities such as cooking, shopping, transportation, or household tasks?",
}


def _domain_for(qid: int) -> str:
    for section in SECTIONS:
        lo, hi = section["range"]
        if lo <= qid <= hi:
            return section["id"]
    raise KeyError(qid)


def _scale_for(qid: int) -> str:
    if 1 <= qid <= 24:
        return "frequency"
    if 25 <= qid <= 27:
        return "change"
    return "independence"


QUESTIONS = [
    {
        "id": qid,
        "text": _QUESTION_TEXT[qid],
        "domain": _domain_for(qid),
        "scale": _scale_for(qid),
    }
    for qid in range(1, 31)
]

QUESTION_IDS = [q["id"] for q in QUESTIONS]

# domain -> list of question ids that feed it
DOMAIN_QUESTIONS = {}
for _q in QUESTIONS:
    DOMAIN_QUESTIONS.setdefault(_q["domain"], []).append(_q["id"])

DOMAIN_IDS = [s["id"] for s in SECTIONS]

DISCLAIMER = (
    "This is a research screening result, not a clinical diagnosis. "
    "It has not been validated against DSM-5 criteria or any diagnostic "
    "reference standard. If you have concerns about your attention, memory, "
    "or thinking, please discuss them with a qualified healthcare professional."
)
