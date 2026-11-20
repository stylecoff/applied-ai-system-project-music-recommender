"""Insights for VibeFinder: history blend, confidence, bias check, diversity.

Everything here works on plain dictionaries and the (song, score, reasons)
tuples that recommend_songs() returns. Nothing here changes recommender.py.

Parts:
1. RECEIPTIFY_TITLES / history_tracks()  - the listening-history snapshot
2. blend_with_history()                  - mix MBTI profile with ticked songs
3. confidence_score()                    - how sure the app is (rule of thumb)
4. bias_check()                          - warnings, never changes the ranking
5. diversify()                           - optional "Mix it up" rule
"""

from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger("vibefinder.insights")

# ---------------------------------------------------------------------------
# 1. Listening-history snapshot
# ---------------------------------------------------------------------------
# A Receiptify snapshot of the author's top tracks "last month". It is NOT a
# live Spotify connection. Titles must match data/songs.csv (ids 21 to 65).
RECEIPTIFY_TITLES = [
    "Back to Friends", "Mary on a Cross", "Fallen Angel", "New Trick",
    "Empire State of Mind (Part II) Broken Down", "Lavender's Blue",
    "U + Me = <3", "Less Than a Lover", "Purple", "Bang Bang",
    "I Love You, I'm Sorry", "Drop Dead", "The Cure", "Mean It",
    "Pumped Up Kicks", "Honeybee", "Godzilla", "Hootie Frutti", "18",
    "8 Letters", "Hold Me Down", "The Bakery", "Spell",
    "I Have a Dream (Remix)", "Everything at Once", "The Show",
    "All We Know", "You're the Inspiration", "Hello My Love", "Iris",
    "Cold Coffee", "Teatime at the Cottage", "Carousel", "Eldest Daughter",
    "Happiest", "Love You More", "Paris in the Rain", "Ain't in LA",
    "To the Bone", "Undressed", "Never Gonna Give You Up", "We Go Up",
    "Goo Goo Muck", "Animal", "Psycho",
]


def history_tracks(songs: list[dict]) -> list[dict]:
    """Return the catalog songs that are in the history snapshot, in snapshot order.

    Titles missing from the catalog are skipped (and logged), so a typo can
    never crash the app.
    """
    by_title = {s["title"].strip().casefold(): s for s in songs}
    found = []
    for title in RECEIPTIFY_TITLES:
        song = by_title.get(title.casefold())
        if song is None:
            logger.warning("History title not in catalog: %s", title)
        else:
            found.append(song)
    return found


# ---------------------------------------------------------------------------
# 2. Blend MBTI profile with listening history
# ---------------------------------------------------------------------------
NUMERIC_KEYS = [
    # (profile key, song field)
    ("target_energy", "energy"),
    ("target_valence", "valence"),
    ("preferred_acousticness", "acousticness"),
    ("preferred_danceability", "danceability"),
    ("preferred_tempo", "tempo_bpm"),
]

MAX_HISTORY_TRACKS_COUNTED = 3   # for the weight and the confidence score
HISTORY_WEIGHT_PER_TRACK = 0.20  # 1 track 20%, 2 tracks 40%, 3 or more 60%


def history_weight(n_tracks: int) -> float:
    """How much the history counts against the MBTI guess (0.0 to 0.6)."""
    if n_tracks <= 0:
        return 0.0
    return round(HISTORY_WEIGHT_PER_TRACK * min(n_tracks, MAX_HISTORY_TRACKS_COUNTED), 2)


def _most_common_majority(values: list[str]) -> str | None:
    """Return the value that at least half of the tracks share, else None."""
    if not values:
        return None
    value, count = Counter(values).most_common(1)[0]
    return value if count / len(values) >= 0.5 else None


def blend_with_history(profile: dict, history: list[dict]) -> dict:
    """Mix an MBTI profile with the numbers of songs the user says they like.

    - Numbers: (1 - w) * MBTI value + w * average of the history songs,
      where w comes from history_weight().
    - Genre and mood: replaced only when at least half of the history songs
      share one; otherwise the MBTI choice stays.
    Returns a new dict. With no history the profile is returned unchanged.
    """
    blended = dict(profile)
    if not history:
        return blended

    w = history_weight(len(history))
    for profile_key, song_field in NUMERIC_KEYS:
        if profile_key not in profile:
            continue
        avg = sum(float(s[song_field]) for s in history) / len(history)
        mixed = (1 - w) * float(profile[profile_key]) + w * avg
        if profile_key == "preferred_tempo":
            blended[profile_key] = round(max(60, min(164, mixed)))
        else:
            blended[profile_key] = round(max(0.0, min(1.0, mixed)), 2)

    genre = _most_common_majority([s["genre"] for s in history])
    mood = _most_common_majority([s["mood"] for s in history])
    if genre:
        blended["favorite_genre"] = genre
    if mood:
        blended["favorite_mood"] = mood

    logger.info("Blended profile with %d history tracks (weight %.2f)", len(history), w)
    return blended


# ---------------------------------------------------------------------------
# 3. Confidence score
# ---------------------------------------------------------------------------
BASE_CONFIDENCE = 30
CONFIDENCE_PER_TRACK = 15

CONFIDENCE_NOTE = "A rule of thumb based on how much information we have, not a probability."


def confidence_score(n_history: int) -> dict:
    """30% with MBTI alone, +15% per history track (up to 3 tracks).

    Returns {"percent": int, "label": "Low" | "Medium" | "Higher", "note": str}.
    """
    n = max(0, min(int(n_history), MAX_HISTORY_TRACKS_COUNTED))
    percent = BASE_CONFIDENCE + CONFIDENCE_PER_TRACK * n
    if percent < 45:
        label = "Low"
    elif percent < 75:
        label = "Medium"
    else:
        label = "Higher"
    return {"percent": percent, "label": label, "note": CONFIDENCE_NOTE}


# ---------------------------------------------------------------------------
# 4. Bias check (warns, never changes the ranking)
# ---------------------------------------------------------------------------
MBTI_GUESS_NOTE = (
    "MBTI is a rough guess about taste. Try neighbouring letters or tick a few "
    "songs you like to see how the list changes."
)

TOP_K_FOR_BIAS = 5
GENRE_DOMINANCE_LIMIT = 3  # this many songs of one genre in the top 5 triggers a warning


def bias_check(results: list[tuple], profile: dict | None = None) -> list[str]:
    """Return a list of plain-English warnings about the top results.

    Rule 1: 3 or more of the top 5 songs share one genre.
    Rule 2: a song that matches only the genre outranks a song that matches
            only the mood (needs the profile to know what "match" means).
    """
    warnings: list[str] = []
    top = results[:TOP_K_FOR_BIAS]
    if not top:
        return warnings

    genre, count = Counter(song["genre"] for song, _, _ in top).most_common(1)[0]
    if count >= GENRE_DOMINANCE_LIMIT:
        warnings.append(
            f"{count} of your top {len(top)} songs are {genre}. "
            "Your results lean heavily on one genre."
        )

    if profile:
        fav_genre = profile.get("favorite_genre")
        fav_mood = profile.get("favorite_mood")
        kinds = []
        for song, _, _ in top:
            g = song["genre"] == fav_genre
            m = song["mood"] == fav_mood
            kinds.append("genre_only" if g and not m else "mood_only" if m and not g else "other")
        genre_beats_mood = any(
            kinds[i] == "genre_only" and kinds[j] == "mood_only"
            for i in range(len(kinds))
            for j in range(i + 1, len(kinds))
        )
        if genre_beats_mood:
            warnings.append(
                "A song that only matches your genre is ranked above a song that only "
                "matches your mood, because a genre match counts double."
            )

    if warnings:
        logger.info("Bias check raised %d warning(s)", len(warnings))
    return warnings


# ---------------------------------------------------------------------------
# 5. "Mix it up": optional diversity rule
# ---------------------------------------------------------------------------
VARIETY_NOTE = "added for variety"


def diversify(ranked: list[tuple], max_per_genre: int = 2, k: int = 5) -> list[tuple]:
    """Pick k songs from a ranked list with at most max_per_genre per genre.

    `ranked` is the (song, score, reasons) list from recommend_songs(), best
    first. Pass the WHOLE ranked catalog: a genre match is worth +2.0, so one
    genre can fill the top 20 and leave nothing to promote.
    Songs that were not in the plain top k get "added for variety" in their
    reasons. If the list runs out of other genres, skipped songs fill the gap.
    Scores are never changed.
    """
    chosen: list[tuple] = []
    skipped: list[tuple] = []
    genre_counts: Counter = Counter()
    plain_top_ids = {id(item[0]) for item in ranked[:k]}

    for item in ranked:
        if len(chosen) >= k:
            break
        genre = item[0]["genre"]
        if genre_counts[genre] < max_per_genre:
            chosen.append(item)
            genre_counts[genre] += 1
        else:
            skipped.append(item)

    for item in skipped:
        if len(chosen) >= k:
            break
        chosen.append(item)

    chosen.sort(key=lambda item: item[1], reverse=True)  # keep the list in score order

    result = []
    for song, score, reasons in chosen:
        if id(song) not in plain_top_ids:
            reasons = f"{reasons}; {VARIETY_NOTE}" if reasons else VARIETY_NOTE
        result.append((song, score, reasons))
    return result