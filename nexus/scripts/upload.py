"""YouTube upload module for the Nexus automation pipeline.

Handles OAuth2 authentication, resumable video upload, and thumbnail
setting via the YouTube Data API v3.
"""

import json
import os
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
CREDENTIALS_PATH = os.path.join(CONFIG_DIR, "youtube_credentials.json")

# Retry settings for resumable uploads
MAX_RETRIES = 5
RETRY_BACKOFF = 2  # seconds, doubled each attempt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[upload] {msg}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def authenticate_youtube():
    """Authenticate with YouTube via OAuth2 and return a service object.

    On the first run an interactive browser flow is triggered using the
    client secret file configured via ``YOUTUBE_CLIENT_SECRET_PATH``.
    Subsequent runs reuse (and refresh) credentials stored at
    ``config/youtube_credentials.json``.

    Returns
    -------
    googleapiclient.discovery.Resource
        An authenticated YouTube Data API v3 service object.
    """
    client_secret_path = settings.get("YOUTUBE_CLIENT_SECRET_PATH", "client_secret.json")
    if not os.path.isfile(client_secret_path):
        raise FileNotFoundError(
            f"YouTube client secret file not found at '{client_secret_path}'. "
            "Set YOUTUBE_CLIENT_SECRET_PATH in your .env file."
        )

    creds = None

    # Try loading existing credentials
    if os.path.isfile(CREDENTIALS_PATH):
        try:
            creds = Credentials.from_authorized_user_file(CREDENTIALS_PATH, SCOPES)
        except Exception as exc:
            _log(f"Could not load saved credentials: {exc}")
            creds = None

    # Refresh or run the full OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            _log("Refreshing expired YouTube credentials...")
            try:
                creds.refresh(Request())
            except Exception as exc:
                _log(f"Refresh failed ({exc}), re-authenticating...")
                creds = None

        if creds is None:
            _log("Starting OAuth2 flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Persist credentials for next time
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CREDENTIALS_PATH, "w") as f:
            f.write(creds.to_json())
        _log(f"Credentials saved to {CREDENTIALS_PATH}")

    service = build("youtube", "v3", credentials=creds)
    _log("YouTube service authenticated successfully")
    return service


def upload_video(
    youtube,
    video_path: str,
    thumbnail_path: str,
    script: dict,
) -> str:
    """Upload a video to YouTube with metadata from *script*.

    Uses a resumable upload so that large files can survive transient
    network failures.  On failure the upload is retried from the last
    successfully sent byte (up to ``MAX_RETRIES`` attempts).

    After the video is uploaded the custom thumbnail is set.

    Parameters
    ----------
    youtube:
        Authenticated YouTube service object (from :func:`authenticate_youtube`).
    video_path:
        Path to the final MP4 file.
    thumbnail_path:
        Path to the thumbnail JPEG.
    script:
        Structured script dict.  Expected keys used for metadata:

        - ``selected_topic`` or first section ``title`` -> video title
        - ``hook`` -> first line of description
        - ``key_points`` -> bullet list in description
        - ``sections`` -> tag extraction

    Returns
    -------
    str
        The YouTube video ID.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # ----- Build metadata from script -----
    title = script.get("selected_topic", "")
    if not title:
        sections = script.get("sections", [])
        title = sections[0].get("title", "Untitled Video") if sections else "Untitled Video"
    # YouTube title max 100 chars
    title = title[:100]

    # Description
    hook = script.get("hook", "")
    key_points = script.get("key_points", [])
    desc_parts = []
    if hook:
        desc_parts.append(hook)
    if key_points:
        desc_parts.append("\nKey points covered:")
        for kp in key_points:
            desc_parts.append(f"  - {kp}")
    desc_parts.append("\n#Shorts #YouTube #AI")
    description = "\n".join(desc_parts)

    # Tags -- pull from sections + niche hints
    tags = []
    for section in script.get("sections", []):
        section_title = section.get("title", "")
        if section_title:
            tags.append(section_title)
    target_audience = script.get("target_audience", "")
    if target_audience:
        tags.append(target_audience)
    # Dedupe and cap at 30
    tags = list(dict.fromkeys(tags))[:30]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # ----- Resumable upload with retry -----
    _log(f"Uploading {video_path} ...")
    response = None
    retries = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                _log(f"Upload progress: {pct}%")
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < MAX_RETRIES:
                retries += 1
                wait = RETRY_BACKOFF ** retries
                _log(f"Server error {exc.resp.status}, retrying in {wait}s (attempt {retries}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"YouTube upload failed after {retries} retries: {exc}"
                ) from exc
        except Exception as exc:
            if retries < MAX_RETRIES:
                retries += 1
                wait = RETRY_BACKOFF ** retries
                _log(f"Upload error: {exc}, retrying in {wait}s (attempt {retries}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"YouTube upload failed after {retries} retries: {exc}"
                ) from exc

    video_id = response["id"]
    _log(f"Video uploaded: https://www.youtube.com/watch?v={video_id}")

    # ----- Set thumbnail -----
    if thumbnail_path and os.path.isfile(thumbnail_path):
        _log("Setting custom thumbnail...")
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            _log("Thumbnail set successfully")
        except HttpError as exc:
            # Thumbnail failure shouldn't block the whole pipeline
            _log(f"Warning: failed to set thumbnail: {exc}")
    else:
        _log("No thumbnail file found, skipping thumbnail upload")

    return video_id


def run(script: dict, video_path: str, thumbnail_path: str) -> str:
    """Authenticate and upload the video to YouTube.

    Parameters
    ----------
    script:
        Structured script / topic dict for metadata.
    video_path:
        Path to the final video MP4.
    thumbnail_path:
        Path to the thumbnail JPEG.

    Returns
    -------
    str
        Full YouTube video URL.
    """
    youtube = authenticate_youtube()
    video_id = upload_video(youtube, video_path, thumbnail_path, script)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    _log(f"Upload complete: {video_url}")
    return video_url


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python upload.py <script.json> <video_path> <thumbnail_path>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        script_data = json.load(f)

    url = run(script_data, sys.argv[2], sys.argv[3])
    print(f"Done: {url}")
