"""Nexus -- YouTube Automation Pipeline

Orchestrates the full video production workflow:
1. Research a topic
2. Generate a script
3. Create voiceover audio
4. Fetch stock visuals
5. Assemble the final video
6. Upload to YouTube
7. Send notifications and log the run
"""

import sys

from scripts.research import research_topic
from scripts.script import generate_script
from scripts.audio import generate_voiceover
from scripts.visuals import download_video, search_stock_videos
from scripts.editor import assemble_video
from scripts.upload import upload_video
from scripts.notify import log_pipeline_run, send_discord_notification


def run_pipeline(topic: str, niche: str = "general") -> None:
    """Execute the full YouTube automation pipeline for a given topic."""

    print(f"\n>>> Starting Nexus pipeline for topic: {topic}\n")

    # Step 1 -- Research
    print("[1/7] Researching topic...")
    research = research_topic(topic, niche)
    print(f"  Research complete ({len(research)} chars)")

    # Step 2 -- Script
    print("[2/7] Generating script...")
    script = generate_script(topic, research=research)
    print(f"  Script generated ({len(script)} chars)")

    # Step 3 -- Audio
    print("[3/7] Generating voiceover...")
    audio_path = generate_voiceover(script)
    print(f"  Audio saved to {audio_path}")

    # Step 4 -- Visuals
    print("[4/7] Fetching stock visuals...")
    videos = search_stock_videos(topic, per_page=5)
    video_paths = []
    for i, video in enumerate(videos):
        path = download_video(video["url"], f"clip_{i}.mp4")
        video_paths.append(path)
    print(f"  Downloaded {len(video_paths)} clips")

    # Step 5 -- Edit
    print("[5/7] Assembling final video...")
    final_path = assemble_video(video_paths, audio_path)
    print(f"  Final video at {final_path}")

    # Step 6 -- Upload
    print("[6/7] Uploading to YouTube...")
    video_id = upload_video(
        video_path=final_path,
        title=topic,
        description=f"An AI-generated video about {topic}.",
        tags=[topic, niche, "AI generated"],
        privacy_status="private",
    )
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  Uploaded: {video_url}")

    # Step 7 -- Notify
    print("[7/7] Sending notifications...")
    send_discord_notification(
        title=f"New Video: {topic}",
        description=f"Pipeline finished successfully.\n{video_url}",
        url=video_url,
    )
    log_pipeline_run(topic=topic, status="success", video_id=video_id)

    print(f"\n>>> Pipeline complete! Video: {video_url}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <topic> [niche]")
        sys.exit(1)

    topic_arg = sys.argv[1]
    niche_arg = sys.argv[2] if len(sys.argv) > 2 else "general"
    run_pipeline(topic_arg, niche_arg)
