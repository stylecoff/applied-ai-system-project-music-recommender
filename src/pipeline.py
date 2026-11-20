"""The VibeFinder pipeline: one function that runs the whole flow.

    validate MBTI -> build profile -> blend history -> score and rank ->
    (optional) mix it up -> confidence and bias check

The app and the evaluation script both call run_pipeline(), so the logic
lives in one place (this is the "orchestration" step in the architecture
diagram). It uses the existing score_song / recommend_songs unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.insights import (
    MBTI_GUESS_NOTE,
    bias_check,
    blend_with_history,
    confidence_score,
    diversify,
)
from src.mbti import explain_profile, profile_from_mbti, type_info, validate_mbti
from src.recommender import load_songs, recommend_songs

logger = logging.getLogger("vibefinder.pipeline")

DEFAULT_SONGS_PATH = Path(__file__).resolve().parent.parent / "data" / "songs.csv"

MIN_K, MAX_K = 1, 10
# genre 2.0 + mood 1.0 + energy 1.5 + valence 1.0 + acousticness 0.8
# + danceability 0.5 + tempo 0.3, with the default weights in recommender.py
MAX_SCORE = 7.1
MIX_MAX_PER_GENRE = 2


@dataclass
class PipelineResult:
    code: str
    type_label: dict                    # name, family, description (display only)
    letter_notes: list[str]             # one line per letter
    mbti_profile: dict                  # profile from the letters alone
    profile: dict                       # after blending with history (may be the same)
    history: list[dict]                 # catalog songs the user said they like
    recommendations: list[dict]         # rank, song, score, match_percent, reasons, variety
    confidence: dict                    # percent, label, note
    warnings: list[str]                 # from the bias check
    guess_note: str = MBTI_GUESS_NOTE
    mix_it_up: bool = False
    skipped_history: list[str] = field(default_factory=list)  # titles not found


def pick_history(songs: list[dict], titles) -> tuple[list[dict], list[str]]:
    """Match the user's chosen titles to catalog songs.

    Returns (songs found, titles not found). Duplicates and blanks are ignored,
    and an unknown title is logged and skipped instead of crashing.
    """
    by_title = {s["title"].strip().casefold(): s for s in songs}
    found, missing, seen = [], [], set()
    for raw in titles or []:
        key = str(raw).strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        song = by_title.get(key)
        if song is None:
            logger.warning("History title not in catalog, skipped: %r", raw)
            missing.append(str(raw))
        else:
            found.append(song)
    return found, missing


def run_pipeline(
    code: str,
    songs: list[dict],
    history_titles=None,
    k: int = 5,
    mix_it_up: bool = False,
) -> PipelineResult:
    """Run the full flow for one user.

    Raises MBTIError for a bad code (the app shows the message) and ValueError
    for an empty catalog. k is kept between 1 and 10.
    """
    code = validate_mbti(code)
    if not songs:
        raise ValueError("The song catalog is empty, so there is nothing to recommend.")
    k = max(MIN_K, min(int(k), MAX_K))

    mbti_profile = profile_from_mbti(code)
    history, missing = pick_history(songs, history_titles)
    profile = blend_with_history(mbti_profile, history)

    # Rank the whole catalog so "Mix it up" has other genres to choose from.
    ranked_all = recommend_songs(profile, songs, k=len(songs))
    if mix_it_up:
        final = diversify(ranked_all, max_per_genre=MIX_MAX_PER_GENRE, k=k)
    else:
        final = ranked_all[:k]

    recommendations = []
    for rank, (song, score, reasons) in enumerate(final, start=1):
        reason_list = [r for r in reasons.split("; ") if r]
        recommendations.append({
            "rank": rank,
            "song": song,
            "score": round(score, 2),
            "match_percent": round(100 * score / MAX_SCORE),
            "reasons": reason_list,
            "variety": any("added for variety" in r for r in reason_list),
        })

    warnings = bias_check(final, profile)
    confidence = confidence_score(len(history))

    logger.info(
        "Pipeline done: code=%s history=%d mix=%s top=%s confidence=%d%% warnings=%d",
        code, len(history), mix_it_up,
        final[0][0]["title"] if final else None, confidence["percent"], len(warnings),
    )

    return PipelineResult(
        code=code,
        type_label=type_info(code),
        letter_notes=explain_profile(code),
        mbti_profile=mbti_profile,
        profile=profile,
        history=history,
        recommendations=recommendations,
        confidence=confidence,
        warnings=warnings,
        mix_it_up=mix_it_up,
        skipped_history=missing,
    )


def load_catalog(path: str | Path = DEFAULT_SONGS_PATH) -> list[dict]:
    """Load songs.csv with the existing load_songs()."""
    songs = load_songs(str(path))
    logger.info("Loaded %d songs from %s", len(songs), path)
    return songs