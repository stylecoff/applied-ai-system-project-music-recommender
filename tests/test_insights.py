import os

import pytest

from src.insights import (
    RECEIPTIFY_TITLES,
    bias_check,
    blend_with_history,
    confidence_score,
    diversify,
    history_tracks,
    history_weight,
)
from src.mbti import profile_from_mbti
from src.recommender import load_songs, recommend_songs

SONGS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")


def song(title, genre="pop", mood="happy", energy=0.5, valence=0.5,
         acousticness=0.5, danceability=0.5, tempo=100):
    return {
        "id": 0, "title": title, "artist": "x", "genre": genre, "mood": mood,
        "energy": energy, "valence": valence, "acousticness": acousticness,
        "danceability": danceability, "tempo_bpm": tempo,
    }


def ranked(*songs):
    """Fake recommend_songs output: best first."""
    return [(s, 10 - i, "genre match (+2.0)") for i, s in enumerate(songs)]


# --- history snapshot --------------------------------------------------------

def test_snapshot_has_45_unique_titles():
    assert len(RECEIPTIFY_TITLES) == 45
    assert len({t.casefold() for t in RECEIPTIFY_TITLES}) == 45


def test_history_tracks_skips_titles_missing_from_catalog():
    catalog = [song("Iris"), song("Purple")]
    found = history_tracks(catalog)
    assert [s["title"] for s in found] == ["Purple", "Iris"] or {s["title"] for s in found} == {"Iris", "Purple"}
    assert len(found) == 2


@pytest.mark.skipif(not os.path.exists(SONGS_CSV), reason="data/songs.csv not found")
def test_every_history_title_exists_in_the_real_catalog():
    songs = load_songs(SONGS_CSV)
    assert len(history_tracks(songs)) == len(RECEIPTIFY_TITLES)


# --- blend -------------------------------------------------------------------

def test_no_history_returns_the_profile_unchanged():
    profile = profile_from_mbti("INFP")
    assert blend_with_history(profile, []) == profile


def test_blend_does_not_change_the_input_profile():
    profile = profile_from_mbti("INFP")
    before = dict(profile)
    blend_with_history(profile, [song("a", energy=1.0)])
    assert profile == before


def test_history_weight_grows_then_caps():
    assert [history_weight(n) for n in (0, 1, 2, 3, 10)] == [0.0, 0.2, 0.4, 0.6, 0.6]


def test_blend_math_with_one_track():
    profile = {"favorite_genre": "lofi", "favorite_mood": "focused", "target_energy": 0.40,
               "target_valence": 0.70, "preferred_acousticness": 0.30,
               "preferred_danceability": 0.60, "preferred_tempo": 100}
    out = blend_with_history(profile, [song("a", energy=1.0, tempo=160)])
    assert out["target_energy"] == 0.52          # 0.8 * 0.40 + 0.2 * 1.0
    assert out["preferred_tempo"] == 112         # 0.8 * 100 + 0.2 * 160


def test_blend_moves_toward_the_history():
    profile = profile_from_mbti("INFP")  # calm
    loud = [song(str(i), energy=0.95) for i in range(3)]
    assert blend_with_history(profile, loud)["target_energy"] > profile["target_energy"]


def test_majority_genre_and_mood_replace_the_mbti_choice():
    profile = profile_from_mbti("INFP")  # indie pop / nostalgic
    history = [song("a", genre="k-pop", mood="intense"),
               song("b", genre="k-pop", mood="intense"),
               song("c", genre="rock", mood="happy")]
    out = blend_with_history(profile, history)
    assert out["favorite_genre"] == "k-pop"
    assert out["favorite_mood"] == "intense"


def test_no_majority_keeps_the_mbti_genre():
    profile = profile_from_mbti("INFP")
    history = [song("a", genre="k-pop", mood="intense"),
               song("b", genre="rock", mood="happy"),
               song("c", genre="lofi", mood="focused")]
    out = blend_with_history(profile, history)
    assert out["favorite_genre"] == "indie pop"
    assert out["favorite_mood"] == "nostalgic"


def test_blend_stays_in_range():
    profile = profile_from_mbti("ESFP")
    out = blend_with_history(profile, [song("a", energy=1.0, tempo=300)] * 3)
    assert 0 <= out["target_energy"] <= 1
    assert 60 <= out["preferred_tempo"] <= 164


# --- confidence --------------------------------------------------------------

@pytest.mark.parametrize("n, percent, label", [
    (0, 30, "Low"), (1, 45, "Medium"), (2, 60, "Medium"), (3, 75, "Higher"), (9, 75, "Higher"),
])
def test_confidence_levels(n, percent, label):
    result = confidence_score(n)
    assert result["percent"] == percent
    assert result["label"] == label
    assert "not a probability" in result["note"]


def test_confidence_ignores_negative_counts():
    assert confidence_score(-4)["percent"] == 30


# --- bias check --------------------------------------------------------------

def test_warns_when_three_of_top_five_share_a_genre():
    results = ranked(song("a"), song("b"), song("c"), song("d", genre="rock"), song("e", genre="lofi"))
    warnings = bias_check(results)
    assert len(warnings) == 1 and "3 of your top 5" in warnings[0]


def test_no_warning_for_varied_results():
    results = ranked(song("a"), song("b"), song("c", genre="rock"), song("d", genre="lofi"), song("e", genre="k-pop"))
    assert bias_check(results) == []


def test_warns_when_genre_only_match_outranks_mood_only_match():
    profile = {"favorite_genre": "indie pop", "favorite_mood": "romantic"}
    results = ranked(
        song("Stupid Song", genre="indie pop", mood="melancholic"),
        song("Heaven", genre="rock", mood="romantic"),
        song("c", genre="lofi", mood="focused"),
    )
    warnings = bias_check(results, profile)
    assert any("genre is ranked above" in w for w in warnings)


def test_no_genre_beats_mood_warning_when_mood_match_is_first():
    profile = {"favorite_genre": "indie pop", "favorite_mood": "romantic"}
    results = ranked(
        song("Heaven", genre="rock", mood="romantic"),
        song("Stupid Song", genre="indie pop", mood="melancholic"),
    )
    assert bias_check(results, profile) == []


def test_bias_check_handles_empty_results():
    assert bias_check([]) == []


# --- diversify ---------------------------------------------------------------

def test_diversify_limits_each_genre_to_two():
    pool = ranked(*[song(f"p{i}") for i in range(4)],
                  song("r1", genre="rock"), song("l1", genre="lofi"), song("k1", genre="k-pop"))
    out = diversify(pool, max_per_genre=2, k=5)
    genres = [s["genre"] for s, _, _ in out]
    assert len(out) == 5
    assert genres.count("pop") == 2


def test_diversify_marks_promoted_songs_and_keeps_scores():
    pool = ranked(song("p1"), song("p2"), song("p3"), song("p4"),
                  song("p5"), song("r1", genre="rock"))
    out = diversify(pool, max_per_genre=2, k=5)
    titles = [s["title"] for s, _, _ in out]
    assert "r1" in titles
    promoted = [r for s, _, r in out if s["title"] == "r1"][0]
    assert "added for variety" in promoted
    original_scores = {s["title"]: sc for s, sc, _ in pool}
    assert all(sc == original_scores[s["title"]] for s, sc, _ in out)


def test_diversify_result_stays_in_score_order():
    pool = ranked(song("p1"), song("p2"), song("p3"), song("p4"), song("p5"),
                  song("r1", genre="rock"))
    scores = [sc for _, sc, _ in diversify(pool, max_per_genre=2, k=5)]
    assert scores == sorted(scores, reverse=True)


def test_diversify_fills_with_skipped_songs_when_only_one_genre_exists():
    pool = ranked(*[song(f"p{i}") for i in range(6)])
    out = diversify(pool, max_per_genre=2, k=5)
    assert len(out) == 5


def test_diversify_with_few_songs_and_empty_input():
    assert diversify([], k=5) == []
    assert len(diversify(ranked(song("a")), k=5)) == 1


def test_diversify_keeps_order_when_nothing_to_change():
    pool = ranked(song("a"), song("b", genre="rock"), song("c", genre="lofi"))
    assert [s["title"] for s, _, _ in diversify(pool, k=3)] == ["a", "b", "c"]


# --- works with the real recommender ----------------------------------------

@pytest.mark.skipif(not os.path.exists(SONGS_CSV), reason="data/songs.csv not found")
def test_full_flow_with_the_real_recommender():
    songs = load_songs(SONGS_CSV)
    history = history_tracks(songs)[:3]
    profile = blend_with_history(profile_from_mbti("INFP"), history)
    results = recommend_songs(profile, songs, k=20)
    final = diversify(results, k=5)
    assert len(final) == 5
    assert isinstance(bias_check(final, profile), list)
    assert confidence_score(len(history))["percent"] == 75