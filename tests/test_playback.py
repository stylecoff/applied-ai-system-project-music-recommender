import json

from src.playback import (
    find_preview,
    get_playback,
    is_same_song,
    playback_for,
    search_links,
)


def itunes(*results):
    """Build a fake fetch that returns the given iTunes-style results."""
    calls = []

    def fetch(url):
        calls.append(url)
        return {"resultCount": len(results), "results": list(results)}

    fetch.calls = calls
    return fetch


RIBS = {"trackName": "Ribs", "artistName": "Lorde",
        "previewUrl": "https://audio.example/ribs.m4a",
        "trackViewUrl": "https://music.apple.com/ribs",
        "artworkUrl100": "https://img.example/ribs.jpg"}


# --- links -------------------------------------------------------------------

def test_search_links_are_encoded():
    links = search_links("U + Me = <3", "Olivia Rodrigo")
    assert links["youtube"].startswith("https://www.youtube.com/results?search_query=")
    assert " " not in links["youtube"] and " " not in links["spotify"]
    assert "%3C3" in links["youtube"] and "%3C3" in links["spotify"]


# --- matching ----------------------------------------------------------------

def test_exact_match():
    assert is_same_song("Ribs", "Lorde", RIBS)


def test_ampersand_and_case_do_not_matter():
    result = {"trackName": "Walking On Sunshine", "artistName": "Katrina & The Waves"}
    assert is_same_song("Walking on Sunshine", "Katrina and the Waves", result)


def test_remaster_suffix_and_brackets_are_ignored():
    result = {"trackName": "Toxicity (Remastered)", "artistName": "System Of A Down"}
    assert is_same_song("Toxicity", "System of a Down", result)
    result = {"trackName": "Heaven - Remastered 2011", "artistName": "Bryan Adams"}
    assert is_same_song("Heaven", "Bryan Adams", result)


def test_wrong_song_by_same_artist_is_rejected():
    result = {"trackName": "Royals", "artistName": "Lorde"}
    assert not is_same_song("Ribs", "Lorde", result)


def test_same_title_by_other_artist_is_rejected():
    result = {"trackName": "Heaven", "artistName": "Depeche Mode"}
    assert not is_same_song("Heaven", "Bryan Adams", result)


def test_missing_fields_do_not_match():
    assert not is_same_song("Ribs", "Lorde", {})


# --- lookup ------------------------------------------------------------------

def test_finds_a_preview_and_skips_wrong_results_first():
    wrong = {"trackName": "Royals", "artistName": "Lorde", "previewUrl": "https://audio.example/royals.m4a"}
    fetch = itunes(wrong, RIBS)
    info = find_preview("Ribs", "Lorde", fetch=fetch, cache_path=None)
    assert info["status"] == "ok"
    assert info["preview_url"] == RIBS["previewUrl"]
    assert info["track_url"] == RIBS["trackViewUrl"]
    assert info["artwork_url"] == RIBS["artworkUrl100"]
    assert "term=Ribs+Lorde" in fetch.calls[0]


def test_result_without_preview_url_is_not_used():
    no_preview = {"trackName": "Ribs", "artistName": "Lorde"}
    info = find_preview("Ribs", "Lorde", fetch=itunes(no_preview), cache_path=None)
    assert info["status"] == "no_match"
    assert info["preview_url"] is None


def test_fictional_song_gets_no_match():
    info = find_preview("Sunrise City", "Neon Echo", fetch=itunes(), cache_path=None)
    assert info["status"] == "no_match"


def test_network_error_returns_error_instead_of_crashing():
    def broken(url):
        raise OSError("network blocked")

    info = find_preview("Ribs", "Lorde", fetch=broken, cache_path=None)
    assert info["status"] == "error"
    assert info["preview_url"] is None


def test_garbage_response_is_handled():
    info = find_preview("Ribs", "Lorde", fetch=lambda url: ["not", "a", "dict"], cache_path=None)
    assert info["status"] == "no_match"


# --- cache -------------------------------------------------------------------

def test_second_lookup_uses_the_cache(tmp_path):
    cache_file = tmp_path / "cache.json"
    fetch = itunes(RIBS)
    first = find_preview("Ribs", "Lorde", fetch=fetch, cache_path=cache_file)
    second = find_preview("Ribs", "Lorde", fetch=fetch, cache_path=cache_file)
    assert len(fetch.calls) == 1
    assert first["from_cache"] is False and second["from_cache"] is True
    assert second["preview_url"] == RIBS["previewUrl"]
    assert "ribs|lorde" in json.loads(cache_file.read_text(encoding="utf-8"))


def test_no_match_is_cached_but_errors_are_not(tmp_path):
    cache_file = tmp_path / "cache.json"
    fetch = itunes()
    find_preview("Sunrise City", "Neon Echo", fetch=fetch, cache_path=cache_file)
    find_preview("Sunrise City", "Neon Echo", fetch=fetch, cache_path=cache_file)
    assert len(fetch.calls) == 1

    def broken(url):
        raise OSError("down")

    find_preview("Ribs", "Lorde", fetch=broken, cache_path=cache_file)
    fetch2 = itunes(RIBS)
    assert find_preview("Ribs", "Lorde", fetch=fetch2, cache_path=cache_file)["status"] == "ok"
    assert len(fetch2.calls) == 1


def test_corrupt_cache_file_is_ignored(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text("{ this is not json", encoding="utf-8")
    info = find_preview("Ribs", "Lorde", fetch=itunes(RIBS), cache_path=cache_file)
    assert info["status"] == "ok"


# --- what the app calls ------------------------------------------------------

def test_get_playback_always_has_links():
    song = {"title": "Sunrise City", "artist": "Neon Echo"}
    info = get_playback(song, fetch=itunes(), cache_path=None)
    assert info["status"] == "no_match"
    assert info["preview_url"] is None
    assert info["links"]["youtube"] and info["links"]["spotify"]


def test_get_playback_with_preview():
    info = get_playback({"title": "Ribs", "artist": "Lorde"}, fetch=itunes(RIBS), cache_path=None)
    assert info["status"] == "ok" and info["preview_url"]


def test_playback_for_is_capped_at_ten_songs():
    songs = [{"title": f"Song {i}", "artist": "X"} for i in range(15)]
    assert len(playback_for(songs, fetch=itunes(), cache_path=None)) == 10