import pytest

from src.mbti import (
    MBTIError,
    MBTI_EXPLAINER,
    TYPE_INFO,
    all_types,
    explain_profile,
    is_valid_mbti,
    profile_from_mbti,
    type_info,
    validate_mbti,
)

ALL_CODES = [
    a + b + c + d
    for a in "EI"
    for b in "SN"
    for c in "TF"
    for d in "JP"
]

SCORER_KEYS = {
    "favorite_genre",
    "favorite_mood",
    "target_energy",
    "target_valence",
    "preferred_acousticness",
    "preferred_danceability",
    "preferred_tempo",
}


# --- guardrail -------------------------------------------------------------

def test_validate_cleans_case_and_spaces():
    assert validate_mbti("  infp ") == "INFP"


@pytest.mark.parametrize("bad", ["", "INF", "INFPX", "XXXX", "ISTQ", "NIFP", "1234", "IN FP"])
def test_validate_rejects_bad_codes(bad):
    with pytest.raises(MBTIError):
        validate_mbti(bad)


@pytest.mark.parametrize("bad", [None, 42, ["I", "N", "F", "P"]])
def test_validate_rejects_non_text(bad):
    with pytest.raises(MBTIError):
        validate_mbti(bad)


def test_is_valid_mbti():
    assert is_valid_mbti("ENTJ")
    assert not is_valid_mbti("EEEE")


def test_error_message_names_the_bad_position():
    with pytest.raises(MBTIError) as err:
        validate_mbti("IXFP")
    assert "Letter 2" in str(err.value)


# --- profile ---------------------------------------------------------------

def test_profile_has_every_key_the_scorer_reads():
    assert set(profile_from_mbti("INFP")) == SCORER_KEYS


def test_infp_profile_matches_the_diagram_mapping():
    p = profile_from_mbti("INFP")
    assert p == {
        "favorite_genre": "indie pop",
        "favorite_mood": "nostalgic",
        "target_energy": 0.40,
        "target_valence": 0.70,
        "preferred_acousticness": 0.30,
        "preferred_danceability": 0.60,
        "preferred_tempo": 95,
    }


def test_estj_profile_matches_the_diagram_mapping():
    p = profile_from_mbti("ESTJ")
    assert p["favorite_genre"] == "rock"
    assert p["favorite_mood"] == "intense"
    assert p["target_energy"] == 0.80
    assert p["target_valence"] == 0.55
    assert p["preferred_tempo"] == 110


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_type_builds_a_profile_in_range(code):
    p = profile_from_mbti(code)
    for key in ("target_energy", "target_valence", "preferred_acousticness", "preferred_danceability"):
        assert 0.0 <= p[key] <= 1.0
    assert 60 <= p["preferred_tempo"] <= 164


def test_introvert_is_calmer_than_extravert():
    assert profile_from_mbti("INFP")["target_energy"] < profile_from_mbti("ENFP")["target_energy"]
    assert profile_from_mbti("INFP")["preferred_tempo"] < profile_from_mbti("ENFP")["preferred_tempo"]


def test_genre_and_mood_tables():
    expected_genre = {"IN": "indie pop", "IS": "lofi", "EN": "pop", "ES": "rock"}
    expected_mood = {"IT": "focused", "IF": "nostalgic", "ET": "intense", "EF": "happy"}
    for code in ALL_CODES:
        p = profile_from_mbti(code)
        assert p["favorite_genre"] == expected_genre[code[0] + code[1]]
        assert p["favorite_mood"] == expected_mood[code[0] + code[2]]


def test_profile_rejects_invalid_code():
    with pytest.raises(MBTIError):
        profile_from_mbti("ABCD")


def test_explain_profile_gives_one_line_per_letter():
    lines = explain_profile("INFP")
    assert len(lines) == 4
    assert lines[0].startswith("I:")


# --- type table and explainer ----------------------------------------------

def test_there_are_16_types_with_name_family_description():
    assert len(TYPE_INFO) == 16
    assert set(TYPE_INFO) == set(ALL_CODES)
    for info in TYPE_INFO.values():
        assert info["name"] and info["family"] and info["description"]


def test_families_match_the_list():
    assert type_info("INTJ")["family"] == "Analysts"
    assert type_info("ENFP")["family"] == "Diplomats"
    assert type_info("ISTJ")["family"] == "Sentinels"
    assert type_info("ESFP")["family"] == "Explorers"
    assert type_info("INFP")["name"] == "Mediator"


def test_each_family_has_four_types():
    counts = {}
    for info in TYPE_INFO.values():
        counts[info["family"]] = counts.get(info["family"], 0) + 1
    assert counts == {"Analysts": 4, "Diplomats": 4, "Sentinels": 4, "Explorers": 4}


def test_all_types_lists_16():
    assert len(all_types()) == 16


def test_explainer_covers_what_it_is_and_the_music_link():
    assert "What is MBTI?" in MBTI_EXPLAINER
    assert "music" in MBTI_EXPLAINER.lower()
    assert "not a proven scientific rule" in MBTI_EXPLAINER