"""In-app song playback for VibeFinder.

For each song we ask the iTunes Search API (no key needed) for a short
preview clip (about 30 seconds) and let Streamlit play it with st.audio.
If nothing trustworthy is found, or the network fails, the app shows
YouTube and Spotify search links instead. Nothing here can crash the app.

Matching is strict on purpose: a preview is used only if the returned title
AND artist look like the song we asked for. Songs in the catalog that are not
real (or not on iTunes) simply get "no preview", never the wrong song.

Live test in a terminal:   python -m src.playback
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, quote_plus, urlencode

logger = logging.getLogger("vibefinder.playback")

ITUNES_URL = "https://itunes.apple.com/search"
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "preview_cache.json"
REQUEST_TIMEOUT_SECONDS = 6
MAX_SONGS_PER_BATCH = 10
USER_AGENT = "VibeFinder-student-project/1.0"

TITLE_MATCH_RATIO = 0.85
ARTIST_MATCH_RATIO = 0.70


# ---------------------------------------------------------------------------
# Links that always work
# ---------------------------------------------------------------------------

def search_links(title: str, artist: str) -> dict:
    """YouTube and Spotify search pages for a song (always available)."""
    query = f"{title} {artist}".strip()
    return {
        "youtube": f"https://www.youtube.com/results?search_query={quote_plus(query)}",
        "spotify": f"https://open.spotify.com/search/{quote(query)}",
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lower-case, '&' to 'and', no brackets or punctuation, one space between words."""
    text = str(text or "").casefold().replace("&", " and ")
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)   # (feat. X), [Remastered]
    text = re.sub(r"\s-\s.*$", " ", text)           # " - Remastered 2011"
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_same_song(title: str, artist: str, result: dict) -> bool:
    """True if an iTunes result looks like the song we asked for."""
    want_title, got_title = _normalize(title), _normalize(result.get("trackName", ""))
    want_artist, got_artist = _normalize(artist), _normalize(result.get("artistName", ""))
    if not want_title or not got_title or not got_artist:
        return False

    title_ok = _similar(want_title, got_title) >= TITLE_MATCH_RATIO
    artist_ok = (
        want_artist in got_artist
        or got_artist in want_artist
        or _similar(want_artist, got_artist) >= ARTIST_MATCH_RATIO
    )
    return title_ok and artist_ok


# ---------------------------------------------------------------------------
# Cache (a small JSON file; a broken file is ignored, never fatal)
# ---------------------------------------------------------------------------

def _cache_key(title: str, artist: str) -> str:
    return f"{_normalize(title)}|{_normalize(artist)}"


def _load_cache(path) -> dict:
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(path, cache: dict) -> None:
    if path is None:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write preview cache: %s", exc)


# ---------------------------------------------------------------------------
# iTunes lookup
# ---------------------------------------------------------------------------

def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def find_preview(title: str, artist: str, fetch=None, cache_path=CACHE_PATH) -> dict:
    """Look up a preview clip for one song.

    Returns a dict with:
      status       "ok", "no_match" or "error"
      preview_url  link to the ~30 second clip, or None
      track_url    the song's page on Apple Music, or None
      artwork_url  small cover image, or None
      from_cache   True if no web request was made

    `fetch` is a function url -> dict (for tests); by default a real request.
    "ok" and "no_match" are cached. "error" is not, so it is retried later.
    """
    fetch = fetch or _http_get_json
    key = _cache_key(title, artist)

    cache = _load_cache(cache_path)
    if key in cache:
        return {**cache[key], "from_cache": True}

    params = urlencode({
        "term": f"{title} {artist}",
        "media": "music",
        "entity": "song",
        "limit": 5,
        "country": "US",
    })

    try:
        payload = fetch(f"{ITUNES_URL}?{params}")
        results = payload.get("results", []) if isinstance(payload, dict) else []
    except Exception as exc:  # network down, blocked, bad JSON: all handled the same way
        logger.warning("iTunes lookup failed for %r by %r: %s", title, artist, exc)
        return {"status": "error", "preview_url": None, "track_url": None,
                "artwork_url": None, "from_cache": False}

    found = {"status": "no_match", "preview_url": None, "track_url": None, "artwork_url": None}
    for result in results:
        if result.get("previewUrl") and is_same_song(title, artist, result):
            found = {
                "status": "ok",
                "preview_url": result["previewUrl"],
                "track_url": result.get("trackViewUrl"),
                "artwork_url": result.get("artworkUrl100"),
            }
            break

    logger.info("Preview lookup for %r by %r: %s", title, artist, found["status"])
    cache[key] = found
    _save_cache(cache_path, cache)
    return {**found, "from_cache": False}


# ---------------------------------------------------------------------------
# What the app calls
# ---------------------------------------------------------------------------

def get_playback(song: dict, fetch=None, cache_path=CACHE_PATH) -> dict:
    """Everything the app needs to play or open one song.

    Returns title, artist, status, preview_url, track_url, artwork_url and
    links (YouTube and Spotify search). Links are always present.
    """
    title, artist = song["title"], song["artist"]
    preview = find_preview(title, artist, fetch=fetch, cache_path=cache_path)
    return {
        "title": title,
        "artist": artist,
        "status": preview["status"],
        "preview_url": preview["preview_url"],
        "track_url": preview["track_url"],
        "artwork_url": preview["artwork_url"],
        "links": search_links(title, artist),
    }


def playback_for(songs: list[dict], fetch=None, cache_path=CACHE_PATH) -> list[dict]:
    """get_playback for a short list of songs (at most 10, to stay polite to the API)."""
    return [get_playback(s, fetch=fetch, cache_path=cache_path)
            for s in songs[:MAX_SONGS_PER_BATCH]]


# ---------------------------------------------------------------------------
# Live test: python -m src.playback
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        ("Ribs", "Lorde"),
        ("Toxicity", "System of a Down"),
        ("Walking on Sunshine", "Katrina and the Waves"),
        ("Sunrise City", "Neon Echo"),  # fictional: expect no preview
    ]
    print("Testing the iTunes preview lookup (cache disabled)...\n")
    for sample_title, sample_artist in samples:
        info = find_preview(sample_title, sample_artist, cache_path=None)
        print(f"{sample_title} - {sample_artist}: {info['status']}")
        if info["preview_url"]:
            print(f"   preview: {info['preview_url']}")
    print("\nExpected: the first three say ok, the last says no_match.")
    print("'error' for every song means the network blocked the request.")