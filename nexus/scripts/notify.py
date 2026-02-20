"""Notification module for sending Discord webhook alerts and logging to Supabase."""

from datetime import datetime, timezone

from discord_webhook import DiscordEmbed, DiscordWebhook

from config.config import settings, supabase_client


def send_discord_notification(
    title: str,
    description: str,
    color: str = "03b2f8",
    url: str | None = None,
) -> bool:
    """Send a notification to Discord via webhook.

    Args:
        title: Embed title.
        description: Embed description.
        color: Hex color for the embed sidebar.
        url: Optional URL to include in the embed.

    Returns:
        True if the notification was sent successfully.
    """
    webhook_url = settings["DISCORD_WEBHOOK_URL"]
    if not webhook_url:
        print("Discord webhook URL not configured, skipping notification.")
        return False

    webhook = DiscordWebhook(url=webhook_url)

    embed = DiscordEmbed(title=title, description=description, color=color)
    embed.set_timestamp()

    if url:
        embed.set_url(url)

    webhook.add_embed(embed)
    response = webhook.execute()

    if response and response.status_code in (200, 204):
        print(f"Discord notification sent: {title}")
        return True

    print(f"Failed to send Discord notification: {response}")
    return False


def log_pipeline_run(
    topic: str,
    status: str,
    video_id: str | None = None,
    error: str | None = None,
) -> None:
    """Log a pipeline run to Supabase for tracking.

    Args:
        topic: The video topic that was processed.
        status: Status of the pipeline run (e.g. 'success', 'failed').
        video_id: YouTube video ID if upload was successful.
        error: Error message if the run failed.
    """
    record = {
        "topic": topic,
        "status": status,
        "video_id": video_id,
        "error": error,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        supabase_client.table("pipeline_runs").insert(record).execute()
        print(f"Pipeline run logged: {topic} - {status}")
    except Exception as e:
        print(f"Failed to log pipeline run to Supabase: {e}")


if __name__ == "__main__":
    send_discord_notification(
        title="Test Notification",
        description="This is a test notification from the Nexus pipeline.",
    )
