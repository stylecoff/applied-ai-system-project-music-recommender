"""MBTI helpers for VibeFinder.

Three jobs:
1. validate_mbti()     - guardrail: only one letter from each pair is accepted.
2. profile_from_mbti() - turn the four letters into the taste-profile keys
                         that score_song / recommend_songs already read.
3. TYPE_INFO + MBTI_EXPLAINER - the 16 type labels and the "What is MBTI?" text.

The profile comes from the LETTERS only. The nicknames and families
(Architect, Analysts, ...) are 16Personalities display labels, not official
MBTI, and they never change the recommendation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("vibefinder.mbti")

# ---------------------------------------------------------------------------
# 1. Guardrail
# ---------------------------------------------------------------------------

PAIRS = (("E", "I"), ("S", "N"), ("T", "F"), ("J", "P"))


class MBTIError(ValueError):
    """Raised when an MBTI code is not valid. The message is safe to show the user."""


def validate_mbti(code) -> str:
    """Return the cleaned, upper-case 4-letter code, or raise MBTIError.

    A valid code has exactly one letter from each pair, in this order:
    E/I, S/N, T/F, J/P (for example INFP or ESTJ).
    """
    if not isinstance(code, str):
        logger.warning("Rejected MBTI input: not text (%r)", type(code).__name__)
        raise MBTIError("Please enter your 4-letter MBTI code, for example INFP.")

    cleaned = code.strip().upper()
    if len(cleaned) != 4:
        logger.warning("Rejected MBTI input: wrong length (%d)", len(cleaned))
        raise MBTIError(
            "An MBTI code has exactly 4 letters, for example INFP. "
            f"You entered {len(cleaned)}."
        )

    for position, (letter, pair) in enumerate(zip(cleaned, PAIRS), start=1):
        if letter not in pair:
            logger.warning("Rejected MBTI input: letter %d is %r", position, letter)
            raise MBTIError(
                f"Letter {position} must be {pair[0]} or {pair[1]}, but you entered '{letter}'. "
                "The order is E/I, then S/N, then T/F, then J/P."
            )

    return cleaned


def is_valid_mbti(code) -> bool:
    """True/False version of validate_mbti, handy for the UI."""
    try:
        validate_mbti(code)
        return True
    except MBTIError:
        return False


# ---------------------------------------------------------------------------
# 2. Letters -> taste profile
# ---------------------------------------------------------------------------

# Starting point before any letter changes it.
BASE_PROFILE = {
    "target_energy": 0.60,
    "target_valence": 0.65,
    "preferred_acousticness": 0.30,
    "preferred_danceability": 0.65,
    "preferred_tempo": 100,
}

# How each letter nudges the numbers. Keys match BASE_PROFILE.
NUDGES = {
    "I": {"target_energy": -0.20, "preferred_danceability": -0.10,
          "preferred_acousticness": +0.10, "preferred_tempo": -15},
    "E": {"target_energy": +0.20, "preferred_danceability": +0.15,
          "preferred_acousticness": -0.10, "preferred_tempo": +15},
    "S": {"preferred_acousticness": +0.10},
    "N": {"preferred_acousticness": -0.10, "target_valence": -0.05},
    "T": {"target_valence": -0.10},
    "F": {"target_valence": +0.10},
    "J": {"preferred_tempo": -5},
    "P": {"preferred_tempo": +10, "preferred_danceability": +0.05},
}

# Genre comes from the I/E letter plus the S/N letter.
GENRE_BY_PAIR = {"IN": "indie pop", "IS": "lofi", "EN": "pop", "ES": "rock"}

# Mood comes from the I/E letter plus the T/F letter.
MOOD_BY_PAIR = {"IT": "focused", "IF": "nostalgic", "ET": "intense", "EF": "happy"}

TEMPO_MIN, TEMPO_MAX = 60, 164  # same range score_song divides by (164 - 60)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def profile_from_mbti(code: str) -> dict:
    """Build the taste profile for a 4-letter code.

    Returns the keys score_song reads:
    favorite_genre, favorite_mood, target_energy, target_valence,
    preferred_acousticness, preferred_danceability, preferred_tempo.
    Raises MBTIError if the code is not valid.
    """
    code = validate_mbti(code)
    ie, sn, tf, jp = code

    values = dict(BASE_PROFILE)
    for letter in code:
        for key, delta in NUDGES[letter].items():
            values[key] += delta

    profile = {
        "favorite_genre": GENRE_BY_PAIR[ie + sn],
        "favorite_mood": MOOD_BY_PAIR[ie + tf],
        "target_energy": round(_clamp(values["target_energy"], 0.0, 1.0), 2),
        "target_valence": round(_clamp(values["target_valence"], 0.0, 1.0), 2),
        "preferred_acousticness": round(_clamp(values["preferred_acousticness"], 0.0, 1.0), 2),
        "preferred_danceability": round(_clamp(values["preferred_danceability"], 0.0, 1.0), 2),
        "preferred_tempo": round(_clamp(values["preferred_tempo"], TEMPO_MIN, TEMPO_MAX)),
    }
    logger.info("Built profile for %s: %s", code, profile)
    return profile


# One plain-English line per letter. Used by the explainer panel and the assistant.
LETTER_MUSIC_HINTS = {
    "I": "Introvert: calmer, quieter music with a lower tempo and lower energy.",
    "E": "Extravert: livelier, louder music with higher energy and a faster tempo.",
    "S": "Sensing: grounded, acoustic sounds you can picture being played live.",
    "N": "Intuition: dreamier, more electronic or abstract sounds.",
    "T": "Thinking: focused, cooler moods (a little less sugary).",
    "F": "Feeling: warm, emotional moods (a little brighter).",
    "J": "Judging: a steady, predictable tempo.",
    "P": "Perceiving: spontaneous, slightly faster and more danceable.",
}


def explain_profile(code: str) -> list[str]:
    """Return one short line per letter, so the app can show WHY songs were picked."""
    code = validate_mbti(code)
    return [f"{letter}: {LETTER_MUSIC_HINTS[letter]}" for letter in code]


# ---------------------------------------------------------------------------
# 3. The 16 types and the "What is MBTI?" text
# ---------------------------------------------------------------------------

FAMILIES = {
    "NT": "Analysts",
    "NF": "Diplomats",
    "SJ": "Sentinels",
    "SP": "Explorers",
}

# code -> (nickname, one-line description). Family is worked out from the letters.
_TYPES = {
    "INTJ": ("Architect", "Imaginative, strategic planner with a plan for everything."),
    "INTP": ("Logician", "Inventive thinker with a thirst for knowledge."),
    "ENTJ": ("Commander", "Bold, determined leader who finds a way or makes one."),
    "ENTP": ("Debater", "Quick-witted thinker who enjoys a good intellectual challenge."),
    "INFJ": ("Advocate", "Quiet, idealistic and driven by a strong sense of purpose."),
    "INFP": ("Mediator", "Gentle, creative and guided by personal values."),
    "ENFJ": ("Protagonist", "Charismatic, inspiring and keen to bring people together."),
    "ENFP": ("Campaigner", "Enthusiastic, creative and sociable free spirit."),
    "ISTJ": ("Logistician", "Practical and fact-minded, reliable above all."),
    "ISFJ": ("Defender", "Warm, dedicated protector of the people they love."),
    "ESTJ": ("Executive", "Organized administrator who brings order and structure."),
    "ESFJ": ("Consul", "Caring, social and eager to help the people around them."),
    "ISTP": ("Virtuoso", "Bold, practical experimenter and master of tools."),
    "ISFP": ("Adventurer", "Flexible, charming artist who enjoys exploring."),
    "ESTP": ("Entrepreneur", "Energetic, perceptive and happiest in the moment."),
    "ESFP": ("Entertainer", "Spontaneous, playful and a natural performer."),
}


def _family_for(code: str) -> str:
    """NT/NF come from the middle letters, SJ/SP from the S plus the last letter."""
    if code[1] == "N":
        return FAMILIES[code[1] + code[2]]
    return FAMILIES[code[1] + code[3]]


TYPE_INFO = {
    code: {"code": code, "name": name, "family": _family_for(code), "description": desc}
    for code, (name, desc) in _TYPES.items()
}


def type_info(code: str) -> dict:
    """Return name, family and description for a valid code (display labels only)."""
    return dict(TYPE_INFO[validate_mbti(code)])


def all_types() -> list[dict]:
    """The 16 types grouped by family order, for a picker in the UI."""
    order = list(FAMILIES.values())
    return sorted(TYPE_INFO.values(), key=lambda t: (order.index(t["family"]), t["code"]))


MBTI_EXPLAINER = """\
What is MBTI?
The Myers-Briggs Type Indicator (MBTI) sorts people into 16 personality types \
using four pairs of preferences:
- E / I: where you get your energy (Extravert or Introvert)
- S / N: how you take in information (Sensing or Intuition)
- T / F: how you make decisions (Thinking or Feeling)
- J / P: how you organize your life (Judging or Perceiving)
Your four letters make a code such as INFP or ESTJ.

How does it connect to music in VibeFinder?
VibeFinder turns each letter into a music preference. Introverts start with calmer, \
quieter songs and extraverts with livelier ones. S leans toward grounded, acoustic \
sounds and N toward dreamier ones. T leans toward focused, cooler moods and F toward \
warm, emotional ones. J keeps the tempo steady and P makes it a little faster and more \
danceable. The letters give a starting taste profile, then the recommender scores every \
song against it.

Good to know
This link is a design choice made for this project, not a proven scientific rule. \
Research on personality and music taste shows only modest connections, and MBTI itself \
is debated by psychologists. Treat the results as a fun starting point for new users \
who have no listening history yet. Type names such as Architect and families such as \
Analysts are 16Personalities labels, shown for fun. They do not change the songs.\
"""