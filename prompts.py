"""Centralized LLM prompt constants and builders for the SSB practice backend.

These strings were previously inlined in server.py; they are kept here so the
prompt text can be reviewed/tuned without touching the server logic.
"""
import json


# --- generate-srt -----------------------------------------------------------
PROMPT = (
    'Generate exactly 60 distinct Situation Reaction Test practice situations for Indian SSB '
    'preparation. Return JSON only: {"questions":[{"id":1,"situation":"..."}]}. Situations must be '
    'realistic, concise, non-military, and varied across family, travel, workplace, conflict, ethics, '
    'emergencies, teamwork, resource constraints, and responsibility. Do not include answers.'
)


# --- analyze-srt ------------------------------------------------------------
ANALYSIS_DIMENSIONS = [
    "Initiative", "Decision Making", "Practicality", "Responsibility", "Leadership",
    "Teamwork", "Adaptability", "Emotional Stability", "Problem Solving", "Social Awareness",
]

ANALYSIS_STRENGTHS = [
    "You attempted to take ownership rather than wait passively.",
    "Your responses are concise and time-aware.",
    "The situations you addressed show a generally practical focus.",
]

ANALYSIS_IMPROVEMENTS = [
    "State the immediate action before the expected outcome.",
    "Where relevant, mention safe escalation or seeking appropriate help.",
    "Avoid assuming ideal conditions; include a practical contingency.",
]

# Strict JSON schema the model must return (kept in sync with server.AnalysisItem).
ANALYSIS_SCHEMA = (
    '{\n'
    '  "summary": "2-4 sentence overall assessment (decision-making and action-taking pattern)",\n'
    '  "dimensions": [{"name": "<one of the 10 names below>", "score": <int 0-100>} x exactly 10],\n'
    '  "strengths": ["<3 overall strengths>"],\n'
    '  "improvements": ["<3 most concrete overall improvements>"],\n'
    '  "items": [{"id": <int>,\n'
    '             "situation": "<the situation text>",\n'
    '             "response": "<candidate answer verbatim, or No response recorded>",\n'
    '             "score": <int 0-10>,\n'
    '             "feedback": "<what was effective or weak in this specific answer>",\n'
    '             "improvement": "<the one most useful thing to improve in this specific answer>"}]\n'
    '}\n'
)


def analysis_prompt(questions: list, responses: dict) -> str:
    """Build the prompt that asks Gemini to evaluate every SRT response individually.

    Every situation is evaluated against its own response (including blanks), then
    one overall assessment is produced. Returns STRICT JSON in ANALYSIS_SCHEMA shape.
    """
    data = json.dumps({"questions": questions, "responses": responses}, ensure_ascii=False)
    return (
        "You are a senior psychologist preparing a candidate for the Indian SSB Situation Reaction "
        "Test. The candidate has answered some of the 60 situations below. Evaluate EVERY response "
        "individually against its own situation, then give one overall assessment. Be specific and "
        "practical; avoid generic boilerplate. Return STRICT JSON only (no markdown, no commentary) "
        "in EXACTLY this shape:\n"
        + ANALYSIS_SCHEMA
        + "Use exactly these 10 dimension names: " + ", ".join(ANALYSIS_DIMENSIONS) + ".\n"
        + "The items array must contain one entry for EVERY question (all 60), in question order, "
        "including blank responses (score 0, feedback: No response recorded, improvement: answer this "
        "situation with a clear, practical first action). Do not return any text outside the JSON. "
        "Here is the data:\n"
        + data
    )
