import logging
import os
from collections import Counter

import pytest

from src.applogging import setup_logging
from src.mbti import MBTIError
from src.pipeline import MAX_SCORE, load_catalog, pick_history, run_pipeline

SONGS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
needs_catalog = pytest.mark.skipif(not os.path.exists(SONGS_CSV), reason="data/songs.csv not found")


def tiny_catalog():
    def s(i, title, genre, mood, energy):
        return {"id": i, "title": title, "artist": "x", "genre": genre, "mood": mood,
                "energy": energy, "valence": 0.5, "acousticness": 0.5,
                "danceability": 0.5, "tempo_bpm": 100}
    return [
        s(1, "A", "pop", "happy", 0.8), s(2, "B", "pop", "happy", 0.7),
        s(3, "C", "pop", "intense", 0.9), s(4, "D", "rock", "intense", 0.9),
        s(5, "E", "lofi", "focused", 0.3), s(6, "F", "jazz", "relaxed", 0.4),
    ]


# --- guardrails ------------------------------------------------------------

def test_bad_code_is_rejected():
    with pytest.raises(MBTIError):
        run_pipeline("ABCD", tiny_catalog())


def test_empty_catalog_is_rejected():
    with pytest.raises(ValueError):
        run_pipeline("INFP", [])


def test_k_is_kept_in_range():
    assert len(run_pipeline("ENFP", tiny_catalog(), k=100).recommendations) == 6
    assert len(run_pipeline("ENFP", tiny_catalog(), k=0).recommendations) == 1


def test_unknown_history_titles_are_skipped_not_fatal():
    result = run_pipeline("INFP", tiny_catalog(), history_titles=["A", "Nope", "  ", "a"])
    assert [s["title"] for s in result.history] == ["A"]
    assert result.skipped_history == ["Nope"]


def test_pick_history_ignores_duplicates_and_case():
    found, missing = pick_history(tiny_catalog(), ["a", "A", "B"])
    assert [s["title"] for s in found] == ["A", "B"]
    assert missing == []


# --- result shape and behavior ---------------------------------------------

def test_result_fields_and_ranking_order():
    result = run_pipeline("ENFP", tiny_catalog(), k=3)
    assert result.code == "ENFP"
    assert result.type_label["name"] == "Campaigner"
    assert len(result.letter_notes) == 4
    ranks = [r["rank"] for r in result.recommendations]
    scores = [r["score"] for r in result.recommendations]
    assert ranks == [1, 2, 3]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= r["match_percent"] <= 100 for r in result.recommendations)
    assert all(isinstance(r["reasons"], list) and r["reasons"] for r in result.recommendations)


def test_lowercase_code_with_spaces_is_cleaned():
    assert run_pipeline("  enfp ", tiny_catalog()).code == "ENFP"


def test_history_raises_confidence_and_changes_the_profile():
    catalog = tiny_catalog()
    plain = run_pipeline("INFP", catalog)
    with_history = run_pipeline("INFP", catalog, history_titles=["C", "D"])
    assert plain.confidence["percent"] == 30
    assert with_history.confidence["percent"] == 60
    assert with_history.profile["target_energy"] > plain.profile["target_energy"]
    assert with_history.mbti_profile == plain.mbti_profile


def test_mix_it_up_limits_genres_and_marks_promoted_songs():
    catalog = tiny_catalog()
    plain = run_pipeline("ENFP", catalog, k=4)
    mixed = run_pipeline("ENFP", catalog, k=4, mix_it_up=True)
    plain_genres = Counter(r["song"]["genre"] for r in plain.recommendations)
    mixed_genres = Counter(r["song"]["genre"] for r in mixed.recommendations)
    assert plain_genres["pop"] == 3
    assert mixed_genres["pop"] == 2
    assert any(r["variety"] for r in mixed.recommendations)
    assert not any(r["variety"] for r in plain.recommendations)


def test_bias_warning_appears_for_a_one_genre_list():
    result = run_pipeline("ENFP", tiny_catalog(), k=3)
    assert any("pop" in w for w in result.warnings)


def test_max_score_matches_the_default_weights():
    assert MAX_SCORE == pytest.approx(2.0 + 1.0 + 1.5 + 1.0 + 0.8 + 0.5 + 0.3)


# --- with the real catalog ---------------------------------------------------

@needs_catalog
def test_all_16_types_get_five_recommendations_from_the_real_catalog():
    songs = load_catalog()
    for code in [a + b + c + d for a in "EI" for b in "SN" for c in "TF" for d in "JP"]:
        result = run_pipeline(code, songs)
        assert len(result.recommendations) == 5, code
        assert result.recommendations[0]["match_percent"] > 60, code


@needs_catalog
def test_mix_it_up_works_on_the_real_catalog_for_an_indie_pop_type():
    songs = load_catalog()
    mixed = run_pipeline("INFP", songs, mix_it_up=True)
    genres = Counter(r["song"]["genre"] for r in mixed.recommendations)
    assert max(genres.values()) <= 2


# --- logging -----------------------------------------------------------------

def test_setup_logging_creates_a_file_and_writes_to_it(tmp_path):
    log_file = tmp_path / "logs" / "test.log"
    path = setup_logging(log_file)
    run_pipeline("INFP", tiny_catalog())
    for handler in logging.getLogger("vibefinder").handlers:
        handler.flush()
    assert path.exists()
    assert "Pipeline done" in path.read_text(encoding="utf-8")
    setup_logging(log_file)  # a second call must not duplicate handlers
    file_handlers = [h for h in logging.getLogger("vibefinder").handlers
                     if getattr(h, "baseFilename", None) == str(log_file.resolve())]
    assert len(file_handlers) == 1