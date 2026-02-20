"""YouTube upload module using the Google YouTube Data API v3."""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config.config import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = "token.json"


def get_youtube_service():
    """Authenticate and return a YouTube API service instance."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret_path = settings["YOUTUBE_CLIENT_SECRET_PATH"]
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "22",
    privacy_status: str = "private",
) -> str:
    """Upload a video to YouTube.

    Args:
        video_path: Path to the video file.
        title: Video title.
        description: Video description.
        tags: List of tags for the video.
        category_id: YouTube category ID (22 = People & Blogs).
        privacy_status: One of 'private', 'unlisted', or 'public'.

    Returns:
        The YouTube video ID of the uploaded video.
    """
    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = request.execute()
    video_id = response["id"]
    print(f"Video uploaded successfully: https://www.youtube.com/watch?v={video_id}")
    return video_id


if __name__ == "__main__":
    print("Upload module loaded. Use upload_video() to upload a video to YouTube.")
