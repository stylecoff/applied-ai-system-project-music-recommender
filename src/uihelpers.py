"""Small helpers for app.py that need no Streamlit, so they can be unit tested."""

from __future__ import annotations

from src.insights import history_weight
from src.mbti import all_types

TEMPO_MIN, TEMPO_MAX = 60, 164

EXAMPLE_QUESTIONS = [
    "Which song should I start with, and why?",
    "How does my type connect to these songs?",
    "What is MBTI?",
]


def type_options() -> list[str]:
    """Labels for the 16-type picker, grouped by family: 'INTJ - Architect (Analysts)'."""
    return [f"{t['code']} - {t['name']} ({t['family']})" for t in all_types()]


def code_from_option(option: str) -> str:
    """Pull the 4-letter code back out of a picker label."""
    return option.split(" ")[0]


def profile_bars(profile: dict) -> list[tuple[str, float, str]]:
    """(label, fraction from 0 to 1, text to show) for each number in the profile."""
    tempo = profile["preferred_tempo"]
    tempo_fraction = (tempo - TEMPO_MIN) / (TEMPO_MAX - TEMPO_MIN)
    return [
        ("Energy", profile["target_energy"], f"{profile['target_energy']:.2f}"),
        ("Happiness (valence)", profile["target_valence"], f"{profile['target_valence']:.2f}"),
        ("Acoustic sound", profile["preferred_acousticness"], f"{profile['preferred_acousticness']:.2f}"),
        ("Danceability", profile["preferred_danceability"], f"{profile['preferred_danceability']:.2f}"),
        ("Tempo", max(0.0, min(1.0, tempo_fraction)), f"{tempo} BPM"),
    ]


def history_summary(result) -> str:
    """One sentence on where the profile came from."""
    n = len(result.history)
    if n == 0:
        return "Built from your four letters only."
    weight = round(history_weight(n) * 100)
    plural = "track" if n == 1 else "tracks"
    return f"Built from your letters, then blended with {n} {plural} you picked (history counts for {weight}%)."


def confidence_tip(n_history: int) -> str:
    if n_history >= 3:
        return "You are at the highest level this app gives. More tracks will not raise it."
    needed = 3 - n_history
    plural = "track" if needed == 1 else "tracks"
    return f"Pick {needed} more {plural} you like to raise it."


def answer_banner(reply: dict) -> tuple[str, str]:
    """(kind, text) for the label above an assistant answer.

    kind is the name of a Streamlit message: 'success', 'warning' or 'error'.
    """
    if reply["source"] == "gemini":
        return "success", "Checked answer from Gemini: every song it named is in your list."
    if reply["source"] == "fallback":
        return (
            "warning",
            "Fallback answer: Gemini was unavailable or named a song outside your list, "
            "so this answer comes from the catalog only.",
        )
    return "error", reply["answer"]


def signature(code: str, history_titles, mix_it_up: bool) -> tuple:
    """Identifies the current settings, so an old assistant answer is not shown for new ones."""
    return (str(code).strip().upper(), tuple(history_titles), bool(mix_it_up))