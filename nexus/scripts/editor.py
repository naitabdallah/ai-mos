"""Video editor module for the Nexus YouTube automation pipeline.

Assembles the final video from section clips and voiceover audio using
ffmpeg-python, and generates a YouTube thumbnail with Pillow.
"""

import json
import os

import ffmpeg
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
VIDEO_DIR = os.path.join(ASSETS_DIR, "video")
FINAL_DIR = os.path.join(ASSETS_DIR, "final")
FINAL_VIDEO = os.path.join(FINAL_DIR, "final_video.mp4")
THUMBNAIL_PATH = os.path.join(FINAL_DIR, "thumbnail.jpg")

# Output specs
WIDTH = 1920
HEIGHT = 1080
FPS = 24
CHANNEL_NAME = "Nexus"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_duration(path: str) -> float:
    """Return the duration of a media file in seconds."""
    try:
        info = ffmpeg.probe(path)
        return float(info["format"]["duration"])
    except Exception:
        return 0.0


def _log(msg: str) -> None:
    print(f"[editor] {msg}")


# ---------------------------------------------------------------------------
# Section clip creation
# ---------------------------------------------------------------------------

def create_section_clip(
    video_paths: list,
    duration: float,
    section_title: str,
    section_index: int = 0,
) -> str:
    """Trim and concatenate raw footage into a single section clip.

    Each clip is scaled to 1920x1080. If the combined footage is shorter
    than *duration* the last clip is looped; if longer it is trimmed.
    A small semi-transparent title overlay is burned in at the bottom-left.

    Parameters
    ----------
    video_paths:
        Raw footage file paths for this section.
    duration:
        Target duration in seconds.
    section_title:
        Text to overlay on the clip.
    section_index:
        Used in the output filename.

    Returns
    -------
    str
        Path to ``assets/video/section_<index>.mp4``.
    """
    if not video_paths:
        raise ValueError(f"No video paths provided for section {section_index}")

    os.makedirs(VIDEO_DIR, exist_ok=True)
    out_path = os.path.join(VIDEO_DIR, f"section_{section_index}.mp4")

    # Build a concat list, trimming / looping to fill *duration*
    concat_list_path = os.path.join(VIDEO_DIR, f"_concat_{section_index}.txt")
    remaining = duration

    entries: list[str] = []
    for vpath in video_paths:
        if remaining <= 0:
            break
        clip_dur = _probe_duration(vpath)
        if clip_dur <= 0:
            continue
        entries.append(vpath)
        remaining -= clip_dur

    # If we still have time left, loop from the beginning
    idx = 0
    while remaining > 0 and entries:
        entries.append(entries[idx % len(entries)])
        remaining -= _probe_duration(entries[idx % len(entries)])
        idx += 1

    with open(concat_list_path, "w") as f:
        for entry in entries:
            f.write(f"file '{os.path.abspath(entry)}'\n")

    # Concatenate, scale, trim to exact duration, and burn in title text
    _log(f"Creating section {section_index} clip ({duration:.1f}s)...")

    # Escape special characters in the title for ffmpeg drawtext
    safe_title = section_title.replace("'", "'\\''").replace(":", "\\:")

    try:
        (
            ffmpeg
            .input(concat_list_path, f="concat", safe=0)
            .filter("scale", WIDTH, HEIGHT, force_original_aspect_ratio="decrease")
            .filter("pad", WIDTH, HEIGHT, "(ow-iw)/2", "(oh-ih)/2")
            .filter("setsar", 1)
            .filter(
                "drawtext",
                text=safe_title,
                fontsize=28,
                fontcolor="white@0.7",
                x=40,
                y=HEIGHT - 60,
                borderw=1,
                bordercolor="black@0.5",
            )
            .output(
                out_path,
                t=duration,
                vcodec="libx264",
                pix_fmt="yuv420p",
                preset="fast",
                r=FPS,
                an=None,  # no audio for section clips
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(
            f"FFmpeg failed creating section {section_index}: {exc}"
        ) from exc
    finally:
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)

    _log(f"Section {section_index} clip saved to {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Final video assembly
# ---------------------------------------------------------------------------

def _create_slate(text: str, duration: float, out_path: str) -> str:
    """Create a black-background slate with centred white text."""
    _log(f"Creating slate: '{text}' ({duration}s)")
    try:
        (
            ffmpeg
            .input(
                f"color=c=black:s={WIDTH}x{HEIGHT}:d={duration}:r={FPS}",
                f="lavfi",
            )
            .filter(
                "drawtext",
                text=text.replace("'", "'\\''").replace(":", "\\:"),
                fontsize=64,
                fontcolor="white",
                x="(w-text_w)/2",
                y="(h-text_h)/2",
            )
            .output(
                out_path,
                vcodec="libx264",
                pix_fmt="yuv420p",
                preset="fast",
                r=FPS,
                an=None,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"FFmpeg slate creation failed: {exc}") from exc
    return out_path


def assemble_video(section_clips: list, audio_path: str, script: dict) -> str:
    """Concatenate section clips with intro/outro and overlay voiceover.

    Layout:
    - 2 s intro (black + channel name)
    - all section clips back-to-back
    - 5 s outro (black + subscribe CTA)
    - voiceover audio mixed over the full timeline

    Output: ``assets/final/final_video.mp4`` at 1920x1080, H.264 + AAC.

    Parameters
    ----------
    section_clips:
        Ordered list of section clip paths.
    audio_path:
        Path to the combined voiceover MP3/WAV.
    script:
        The structured script dict (used for title / CTA text).

    Returns
    -------
    str
        Path to the final video.
    """
    if not section_clips:
        raise ValueError("No section clips to assemble.")

    os.makedirs(FINAL_DIR, exist_ok=True)

    # Create intro and outro slates
    intro_path = os.path.join(VIDEO_DIR, "_intro.mp4")
    outro_path = os.path.join(VIDEO_DIR, "_outro.mp4")

    _create_slate(CHANNEL_NAME, 2.0, intro_path)

    cta_text = script.get("cta", "Subscribe for more!")
    if len(cta_text) > 60:
        cta_text = "Subscribe for more!"
    _create_slate(cta_text, 5.0, outro_path)

    # Build concat file: intro + sections + outro
    all_clips = [intro_path] + list(section_clips) + [outro_path]
    concat_path = os.path.join(VIDEO_DIR, "_final_concat.txt")
    with open(concat_path, "w") as f:
        for clip in all_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    # Concatenate video (no audio yet)
    video_only = os.path.join(VIDEO_DIR, "_video_only.mp4")
    _log("Concatenating all clips...")
    try:
        (
            ffmpeg
            .input(concat_path, f="concat", safe=0)
            .output(
                video_only,
                vcodec="libx264",
                pix_fmt="yuv420p",
                preset="fast",
                r=FPS,
                an=None,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"FFmpeg concat failed: {exc}") from exc

    # Mux voiceover audio onto video
    _log("Muxing voiceover audio...")
    video_dur = _probe_duration(video_only)
    try:
        video_in = ffmpeg.input(video_only)
        audio_in = ffmpeg.input(audio_path)
        (
            ffmpeg
            .output(
                video_in.video,
                audio_in.audio,
                FINAL_VIDEO,
                vcodec="copy",
                acodec="aac",
                shortest=None,
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"FFmpeg audio mux failed: {exc}") from exc

    # Clean up temp files
    for tmp in (intro_path, outro_path, concat_path, video_only):
        if os.path.exists(tmp):
            os.remove(tmp)

    _log(f"Final video saved to {FINAL_VIDEO}")
    return FINAL_VIDEO


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------

def generate_thumbnail(script: dict) -> str:
    """Create a 1280x720 YouTube thumbnail with Pillow.

    Uses a dark gradient background with the video title in large bold
    white text, centred.

    Parameters
    ----------
    script:
        The structured script dict; uses ``selected_topic`` or falls
        back to the first section title for the text.

    Returns
    -------
    str
        Path to ``assets/final/thumbnail.jpg``.
    """
    os.makedirs(FINAL_DIR, exist_ok=True)

    thumb_w, thumb_h = 1280, 720

    # Dark gradient background
    img = Image.new("RGB", (thumb_w, thumb_h), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)

    # Add a subtle gradient overlay
    for y in range(thumb_h):
        alpha = int(40 * (y / thumb_h))
        draw.line([(0, y), (thumb_w, y)], fill=(alpha, alpha, alpha + 10))

    # Determine title text
    title = script.get("selected_topic", "")
    if not title:
        sections = script.get("sections", [])
        title = sections[0].get("title", "Video") if sections else "Video"

    # Try to use a bold system font; fall back to default
    font = None
    font_sizes = [72, 60, 48, 36]
    preferred_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]

    for fpath in preferred_fonts:
        if os.path.exists(fpath):
            font = ImageFont.truetype(fpath, font_sizes[0])
            break

    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", font_sizes[0])
        except OSError:
            font = ImageFont.load_default()

    # Word-wrap the title to fit within the image
    max_chars_per_line = 28
    words = title.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        if len(test) > max_chars_per_line and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    # Draw each line centred vertically
    line_height = font.size if hasattr(font, "size") else 40
    total_text_height = line_height * len(lines)
    y_start = (thumb_h - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (thumb_w - text_w) // 2
        y = y_start + i * line_height

        # Shadow
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=font)
        # Main text
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    # Add a coloured accent bar at the bottom
    draw.rectangle([(0, thumb_h - 8), (thumb_w, thumb_h)], fill=(220, 50, 50))

    img.save(THUMBNAIL_PATH, "JPEG", quality=95)
    _log(f"Thumbnail saved to {THUMBNAIL_PATH}")
    return THUMBNAIL_PATH


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(script: dict, visuals_map: dict, audio_path: str) -> dict:
    """Orchestrate the full video assembly pipeline.

    1. Create a section clip for each entry in *visuals_map*.
    2. Assemble the final video with intro, outro, and voiceover.
    3. Generate a thumbnail.

    Parameters
    ----------
    script:
        Structured script dict.
    visuals_map:
        Section-index-to-file-paths mapping (from visuals step).
    audio_path:
        Path to the combined voiceover audio.

    Returns
    -------
    dict
        ``{video_path: str, thumbnail_path: str}``.
    """
    sections = script.get("sections", [])

    # Estimate per-section duration from total audio
    audio_dur = _probe_duration(audio_path)
    num_sections = max(len(sections), 1)
    # Reserve 7 seconds for intro (2s) + outro (5s)
    content_dur = max(audio_dur - 7.0, num_sections * 5.0)
    per_section = content_dur / num_sections

    # Step 1 -- create section clips
    section_clips: list[str] = []
    for idx, section in enumerate(sections):
        paths = visuals_map.get(str(idx), visuals_map.get(idx, []))
        if not paths:
            _log(f"Section {idx} has no footage, skipping clip creation")
            continue

        title = section.get("title", f"Section {idx + 1}")
        clip_path = create_section_clip(paths, per_section, title, idx)
        section_clips.append(clip_path)

    if not section_clips:
        raise RuntimeError("No section clips were created -- cannot assemble video.")

    # Step 2 -- assemble final video
    video_path = assemble_video(section_clips, audio_path, script)

    # Step 3 -- thumbnail
    thumbnail_path = generate_thumbnail(script)

    return {"video_path": video_path, "thumbnail_path": thumbnail_path}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python editor.py <script.json> <visuals_map.json> <audio_path>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        script_data = json.load(f)
    with open(sys.argv[2], "r") as f:
        vis_map = json.load(f)

    result = run(script_data, vis_map, sys.argv[3])
    print(json.dumps(result, indent=2))
