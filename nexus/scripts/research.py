"""Research module for the Nexus YouTube automation pipeline.

Finds trending video topics for a given niche using the YouTube Data API v3,
then uses Claude 3.5 Sonnet (via AWS Bedrock) to pick the single best topic.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from config.config import bedrock_client, settings, youtube_client

# Path to save research output
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTPUT_PATH = os.path.join(ASSETS_DIR, "research_output.json")


# ---------------------------------------------------------------------------
# YouTube trending-topic discovery
# ---------------------------------------------------------------------------

def get_trending_topics(niche: str, max_results: int = 20) -> list:
    """Search YouTube for recent high-engagement videos in *niche*.

    Calls the YouTube Data API v3 ``search.list`` endpoint for videos
    published in the last 30 days, then enriches each result with
    statistics (views, likes, comments) via ``videos.list``.

    Parameters
    ----------
    niche:
        Search query / niche keyword (e.g. "AI tools", "personal finance").
    max_results:
        Maximum number of results to return (capped at 50 by the API).

    Returns
    -------
    list[dict]
        Each dict contains: ``title``, ``video_id``, ``views``, ``likes``,
        ``channel``, ``published_at``.  The list is sorted by view count
        (descending).
    """
    if youtube_client is None:
        raise RuntimeError(
            "YouTube client is not initialised. "
            "Set YOUTUBE_API_KEY in your .env file."
        )

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1 -- search for recent videos in the niche
    search_response = (
        youtube_client.search()
        .list(
            q=niche,
            part="snippet",
            type="video",
            order="viewCount",
            publishedAfter=published_after,
            maxResults=min(max_results, 50),
        )
        .execute()
    )

    video_ids = [
        item["id"]["videoId"]
        for item in search_response.get("items", [])
        if item["id"].get("videoId")
    ]

    if not video_ids:
        return []

    # Step 2 -- fetch statistics for each video
    stats_response = (
        youtube_client.videos()
        .list(
            id=",".join(video_ids),
            part="snippet,statistics",
        )
        .execute()
    )

    topics: list[dict] = []
    for item in stats_response.get("items", []):
        stats = item.get("statistics", {})
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        # Basic engagement filter -- skip videos with negligible interaction
        if views < 1000 or (likes + comments) < 10:
            continue

        topics.append(
            {
                "title": item["snippet"]["title"],
                "video_id": item["id"],
                "views": views,
                "likes": likes,
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
            }
        )

    # Sort by views descending and cap at max_results
    topics.sort(key=lambda t: t["views"], reverse=True)
    return topics[:max_results]


# ---------------------------------------------------------------------------
# Claude-powered topic analysis
# ---------------------------------------------------------------------------

def analyze_topics(topics: list, niche: str) -> dict:
    """Use Claude 3.5 Sonnet to pick the single best topic from *topics*.

    Sends the list of trending videos to Bedrock and asks Claude to
    identify patterns and select one topic worth covering, returning
    structured JSON.

    Parameters
    ----------
    topics:
        List of topic dicts as returned by :func:`get_trending_topics`.
    niche:
        The niche / category being targeted.

    Returns
    -------
    dict
        Keys: ``selected_topic``, ``angle``, ``why``, ``target_audience``,
        ``key_points`` (list of strings).
    """
    if bedrock_client is None:
        raise RuntimeError(
            "Bedrock client is not initialised. "
            "Check your AWS credentials in the .env file."
        )

    if not topics:
        raise ValueError("No topics provided for analysis.")

    topics_text = json.dumps(topics, indent=2, default=str)

    prompt = (
        f"You are a YouTube content strategist specialising in the "
        f'"{niche}" niche.\n\n'
        f"Below is a list of trending YouTube videos from the last 30 days "
        f"in this niche:\n\n"
        f"{topics_text}\n\n"
        f"Analyse the patterns in these trending topics. Consider view counts, "
        f"engagement, titles, and timing. Then select the single best topic "
        f"idea for a NEW YouTube video that could capitalise on these trends.\n\n"
        f"Return your answer as JSON with exactly these keys:\n"
        f"- selected_topic: the topic title for the new video\n"
        f"- angle: the unique angle or hook\n"
        f"- why: why this topic will perform well right now\n"
        f"- target_audience: who this video is for\n"
        f"- key_points: a list of 4-6 key points to cover in the video\n\n"
        f"Return ONLY valid JSON, no markdown fences or extra text."
    )

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
    )

    response = bedrock_client.invoke_model(
        modelId=settings["BEDROCK_MODEL_ID"],
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    raw_text: str = result["content"][0]["text"]

    # Strip markdown code fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    parsed: dict = json.loads(cleaned.strip())

    # Validate expected keys
    expected_keys = {"selected_topic", "angle", "why", "target_audience", "key_points"}
    missing = expected_keys - set(parsed.keys())
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")

    return parsed


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(niche: str) -> dict:
    """Run the full research step: discover trending topics then analyse them.

    1. Calls :func:`get_trending_topics` for the given *niche*.
    2. Passes the results to :func:`analyze_topics`.
    3. Saves the output to ``assets/research_output.json``.

    Parameters
    ----------
    niche:
        The YouTube niche to research (e.g. "tech reviews").

    Returns
    -------
    dict
        The analysis dict produced by :func:`analyze_topics`.
    """
    print(f"[research] Fetching trending topics for niche: {niche}")
    topics = get_trending_topics(niche)
    print(f"[research] Found {len(topics)} trending topics")

    print("[research] Analysing topics with Claude...")
    analysis = analyze_topics(topics, niche)
    print(f"[research] Selected topic: {analysis.get('selected_topic', 'N/A')}")

    # Persist to disk
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"[research] Saved output to {OUTPUT_PATH}")

    return analysis


if __name__ == "__main__":
    import sys

    niche_arg = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence"
    result = run(niche_arg)
    print(json.dumps(result, indent=2))
