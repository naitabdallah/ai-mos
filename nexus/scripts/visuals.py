"""Visuals module for the Nexus YouTube automation pipeline.

Downloads relevant stock footage for each script section using the
Pexels video search API, with fallback query simplification when no
results are found.
"""

import json
import os
import re

import requests

from config.config import settings

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
RAW_DIR = os.path.join(ASSETS_DIR, "raw")
VISUALS_MAP_PATH = os.path.join(ASSETS_DIR, "visuals_map.json")

PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

# Preferred resolution and duration bounds
PREFERRED_WIDTH = 1920
PREFERRED_HEIGHT = 1080
MIN_DURATION = 5
MAX_DURATION = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simplify_query(query: str) -> str:
    """Strip common adjectives / filler words to broaden the search.

    Removes words that are typically decorative rather than essential
    (e.g. "stunning", "beautiful", "amazing") so Pexels has a better
    chance of returning results.
    """
    filler = {
        "stunning", "beautiful", "amazing", "incredible", "gorgeous",
        "dramatic", "epic", "cinematic", "breathtaking", "vibrant",
        "colorful", "dynamic", "powerful", "intense", "serene",
        "majestic", "elegant", "subtle", "bold", "striking",
        "very", "really", "extremely", "highly", "super",
    }
    words = query.split()
    simplified = [w for w in words if w.lower() not in filler]
    return " ".join(simplified) if simplified else query


def _pick_best_file(video_files: list, duration: int | None) -> dict | None:
    """Select the best video file from a Pexels result.

    Prefers HD (1920x1080) landscape files.  Falls back to the largest
    available file if no exact HD match exists.
    """
    if not video_files:
        return None

    # Filter to landscape-ish files
    landscape = [
        f for f in video_files
        if (f.get("width") or 0) >= (f.get("height") or 0)
    ]
    pool = landscape if landscape else video_files

    # Prefer exact HD match
    for f in pool:
        if f.get("width") == PREFERRED_WIDTH and f.get("height") == PREFERRED_HEIGHT:
            return f

    # Otherwise pick highest resolution
    pool.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), reverse=True)
    return pool[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_footage(visual_cue: str, count: int = 3) -> list:
    """Search Pexels for stock video clips matching *visual_cue*.

    Parameters
    ----------
    visual_cue:
        Descriptive search string (e.g. "person typing on laptop").
    count:
        Maximum number of clips to return.

    Returns
    -------
    list[dict]
        Each dict: ``url``, ``width``, ``height``, ``duration``, ``thumbnail``.
    """
    api_key = settings.get("PEXELS_API_KEY", "")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is not set in your .env file.")

    headers = {"Authorization": api_key}

    def _search(query: str) -> list:
        resp = requests.get(
            PEXELS_VIDEO_SEARCH_URL,
            headers=headers,
            params={"query": query, "per_page": count * 2, "orientation": "landscape"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("videos", [])

    # First attempt with the original cue
    videos = _search(visual_cue)

    # Fallback: simplify the query if nothing came back
    if not videos:
        simplified = _simplify_query(visual_cue)
        if simplified != visual_cue:
            print(f"[visuals] No results for '{visual_cue}', retrying with '{simplified}'")
            videos = _search(simplified)

    results: list[dict] = []
    for video in videos:
        duration = video.get("duration", 0)
        if duration < MIN_DURATION or duration > MAX_DURATION:
            continue

        best = _pick_best_file(video.get("video_files", []), duration)
        if best is None:
            continue

        # Grab a thumbnail from the first picture entry
        pictures = video.get("video_pictures", [])
        thumbnail = pictures[0]["picture"] if pictures else ""

        results.append(
            {
                "url": best["link"],
                "width": best.get("width"),
                "height": best.get("height"),
                "duration": duration,
                "thumbnail": thumbnail,
            }
        )

        if len(results) >= count:
            break

    return results


def download_footage(footage_list: list, section_index: int) -> list:
    """Download video clips to ``assets/raw/section_<index>_<n>.mp4``.

    Parameters
    ----------
    footage_list:
        List of footage dicts (as returned by :func:`search_footage`).
    section_index:
        The script section number, used in the filename.

    Returns
    -------
    list[str]
        Local file paths of downloaded clips.
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    paths: list[str] = []

    for count, clip in enumerate(footage_list):
        url = clip.get("url", "")
        if not url:
            continue

        filename = f"section_{section_index}_{count}.mp4"
        out_path = os.path.join(RAW_DIR, filename)

        try:
            print(f"[visuals] Downloading {filename}...")
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()

            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            paths.append(out_path)
        except requests.RequestException as exc:
            print(f"[visuals] Failed to download {url}: {exc}")
            continue

    return paths


def get_visuals_for_script(script: dict) -> dict:
    """Fetch stock footage for every section in *script*.

    Iterates through ``script["sections"]`` and uses each section's
    ``visual_cue`` field to search and download clips.

    Parameters
    ----------
    script:
        Structured script dict with a ``sections`` list.  Each section
        should have a ``visual_cue`` key.

    Returns
    -------
    dict
        Mapping of section index (as string) to list of local video paths.
    """
    sections = script.get("sections", [])
    if not sections:
        raise ValueError("Script contains no sections.")

    visuals_map: dict[str, list[str]] = {}

    for index, section in enumerate(sections):
        cue = section.get("visual_cue", "")
        if not cue:
            print(f"[visuals] Section {index} has no visual_cue, skipping")
            visuals_map[str(index)] = []
            continue

        print(f"[visuals] Section {index}: searching for '{cue}'")
        footage = search_footage(cue)

        if not footage:
            print(f"[visuals] No footage found for section {index}")
            visuals_map[str(index)] = []
            continue

        downloaded = download_footage(footage, index)
        visuals_map[str(index)] = downloaded
        print(f"[visuals] Section {index}: downloaded {len(downloaded)} clips")

    return visuals_map


def run(script: dict) -> dict:
    """Run the full visuals step and persist the mapping.

    1. Calls :func:`get_visuals_for_script`.
    2. Saves the mapping to ``assets/visuals_map.json``.

    Parameters
    ----------
    script:
        Structured script dict.

    Returns
    -------
    dict
        Section-index-to-file-paths mapping.
    """
    visuals_map = get_visuals_for_script(script)

    os.makedirs(os.path.dirname(VISUALS_MAP_PATH), exist_ok=True)
    with open(VISUALS_MAP_PATH, "w") as f:
        json.dump(visuals_map, f, indent=2)
    print(f"[visuals] Saved visuals map to {VISUALS_MAP_PATH}")

    return visuals_map


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python visuals.py <script.json>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        script_data = json.load(f)

    result = run(script_data)
    print(json.dumps(result, indent=2))
