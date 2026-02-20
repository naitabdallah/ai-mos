"""Central configuration module for the Nexus YouTube automation pipeline.

Loads environment variables and initializes API clients for:
- AWS Bedrock (LLM inference)
- ElevenLabs (text-to-speech)
- Supabase (database / logging)
"""

import os
import sys

import boto3
from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from supabase import Client, create_client

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Settings dictionary -- all env vars in one place
# ---------------------------------------------------------------------------
settings: dict[str, str] = {
    "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
    "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
    "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
    "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
    "ELEVENLABS_API_KEY": os.getenv("ELEVENLABS_API_KEY", ""),
    "ELEVENLABS_VOICE_ID": os.getenv("ELEVENLABS_VOICE_ID", ""),
    "YOUTUBE_CLIENT_SECRET_PATH": os.getenv("YOUTUBE_CLIENT_SECRET_PATH", "client_secret.json"),
    "PEXELS_API_KEY": os.getenv("PEXELS_API_KEY", ""),
    "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
    "SUPABASE_KEY": os.getenv("SUPABASE_KEY", ""),
    "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", ""),
}

# ---------------------------------------------------------------------------
# AWS Bedrock client
# ---------------------------------------------------------------------------
try:
    bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        region_name=settings["AWS_REGION"],
        aws_access_key_id=settings["AWS_ACCESS_KEY_ID"] or None,
        aws_secret_access_key=settings["AWS_SECRET_ACCESS_KEY"] or None,
    )
except Exception as e:
    print(f"[config] Failed to create AWS Bedrock client: {e}")
    bedrock_client = None

# ---------------------------------------------------------------------------
# ElevenLabs client
# ---------------------------------------------------------------------------
try:
    elevenlabs_client = ElevenLabs(api_key=settings["ELEVENLABS_API_KEY"] or None)
except Exception as e:
    print(f"[config] Failed to create ElevenLabs client: {e}")
    elevenlabs_client = None

# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
try:
    if settings["SUPABASE_URL"] and settings["SUPABASE_KEY"]:
        supabase_client: Client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_KEY"])
    else:
        print("[config] Supabase URL or key not set -- client not initialised.")
        supabase_client = None
except Exception as e:
    print(f"[config] Failed to create Supabase client: {e}")
    supabase_client = None


# ---------------------------------------------------------------------------
# Connection test helper
# ---------------------------------------------------------------------------
def test_connections() -> None:
    """Test each configured API connection and print status."""

    print("=" * 50)
    print("  Nexus -- Connection Tests")
    print("=" * 50)

    # --- AWS Bedrock ---
    try:
        if bedrock_client is None:
            raise RuntimeError("Bedrock client was not initialised")
        bedrock_client.list_foundation_models(maxResults=1)
        print("[OK]   AWS Bedrock: connected")
    except Exception as e:
        print(f"[FAIL] AWS Bedrock: {e}")

    # --- ElevenLabs ---
    try:
        if elevenlabs_client is None:
            raise RuntimeError("ElevenLabs client was not initialised")
        elevenlabs_client.voices.get_all()
        print("[OK]   ElevenLabs: connected")
    except Exception as e:
        print(f"[FAIL] ElevenLabs: {e}")

    # --- Supabase ---
    try:
        if supabase_client is None:
            raise RuntimeError("Supabase client was not initialised")
        # Simple health-check query
        supabase_client.table("pipeline_runs").select("*").limit(1).execute()
        print("[OK]   Supabase: connected")
    except Exception as e:
        print(f"[FAIL] Supabase: {e}")

    # --- Pexels ---
    try:
        import requests

        if not settings["PEXELS_API_KEY"]:
            raise RuntimeError("PEXELS_API_KEY not set")
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": settings["PEXELS_API_KEY"]},
            params={"query": "test", "per_page": 1},
            timeout=10,
        )
        resp.raise_for_status()
        print("[OK]   Pexels API: connected")
    except Exception as e:
        print(f"[FAIL] Pexels API: {e}")

    # --- Discord Webhook ---
    try:
        if not settings["DISCORD_WEBHOOK_URL"]:
            raise RuntimeError("DISCORD_WEBHOOK_URL not set")
        print("[OK]   Discord Webhook: URL configured")
    except Exception as e:
        print(f"[FAIL] Discord Webhook: {e}")

    print("=" * 50)


if __name__ == "__main__":
    test_connections()
