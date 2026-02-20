"""Visuals module for fetching stock footage from the Pexels API."""

import os

import requests

from config.config import settings

VIDEO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "video")
RAW_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "raw")

PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"


def search_stock_videos(query: str, per_page: int = 5) -> list[dict]:
    """Search for stock videos on Pexels.

    Args:
        query: Search term for finding relevant videos.
        per_page: Number of results to return.

    Returns:
        A list of video metadata dicts with download URLs.
    """
    headers = {"Authorization": settings["PEXELS_API_KEY"]}
    params = {"query": query, "per_page": per_page}

    response = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params)
    response.raise_for_status()

    data = response.json()
    videos = []

    for video in data.get("videos", []):
        # Pick the HD file if available
        video_files = video.get("video_files", [])
        hd_files = [f for f in video_files if f.get("quality") == "hd"]
        best_file = hd_files[0] if hd_files else (video_files[0] if video_files else None)

        if best_file:
            videos.append(
                {
                    "id": video["id"],
                    "url": best_file["link"],
                    "width": best_file.get("width"),
                    "height": best_file.get("height"),
                    "duration": video.get("duration"),
                }
            )

    return videos


def download_video(url: str, filename: str) -> str:
    """Download a video from a URL and save it locally.

    Args:
        url: Direct download URL for the video.
        filename: Name to save the file as.

    Returns:
        Path to the downloaded file.
    """
    os.makedirs(RAW_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(RAW_OUTPUT_DIR, filename)

    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Downloaded video to {output_path}")
    return output_path


if __name__ == "__main__":
    results = search_stock_videos("technology")
    for i, video in enumerate(results):
        print(f"Video {i + 1}: {video['url']} ({video['duration']}s)")
