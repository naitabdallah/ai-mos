"""Video editor module for assembling the final video using MoviePy."""

import os

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

FINAL_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "final")


def assemble_video(
    video_clips: list[str],
    audio_path: str,
    output_filename: str = "final_video.mp4",
    resolution: tuple[int, int] = (1920, 1080),
) -> str:
    """Assemble video clips with an audio voiceover into a final video.

    Args:
        video_clips: List of paths to video clip files.
        audio_path: Path to the voiceover audio file.
        output_filename: Name of the final output file.
        resolution: Target resolution as (width, height).

    Returns:
        Path to the final assembled video.
    """
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(FINAL_OUTPUT_DIR, output_filename)

    # Load and resize all video clips
    clips = []
    for clip_path in video_clips:
        clip = VideoFileClip(clip_path).resize(resolution)
        clips.append(clip)

    # Concatenate video clips
    video = concatenate_videoclips(clips, method="compose")

    # Load and attach audio
    audio = AudioFileClip(audio_path)

    # Trim video to match audio length or vice versa
    if video.duration > audio.duration:
        video = video.subclip(0, audio.duration)
    elif audio.duration > video.duration:
        # Loop video to match audio length
        loops_needed = int(audio.duration / video.duration) + 1
        video = concatenate_videoclips([video] * loops_needed).subclip(0, audio.duration)

    video = video.set_audio(audio)

    # Export
    video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=24,
    )

    # Clean up
    video.close()
    audio.close()
    for clip in clips:
        clip.close()

    print(f"Final video saved to {output_path}")
    return output_path


def add_text_overlay(
    video_path: str,
    text: str,
    output_filename: str = "video_with_text.mp4",
    fontsize: int = 48,
    color: str = "white",
    position: str = "bottom",
) -> str:
    """Add a text overlay to a video.

    Args:
        video_path: Path to the input video.
        text: Text to overlay on the video.
        output_filename: Name of the output file.
        fontsize: Font size for the text.
        color: Text color.
        position: Position of the text on the video.

    Returns:
        Path to the video with text overlay.
    """
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(FINAL_OUTPUT_DIR, output_filename)

    video = VideoFileClip(video_path)
    txt_clip = TextClip(text, fontsize=fontsize, color=color).set_duration(video.duration).set_position(position)

    result = CompositeVideoClip([video, txt_clip])
    result.write_videofile(output_path, codec="libx264", audio_codec="aac")

    video.close()
    result.close()

    print(f"Video with text overlay saved to {output_path}")
    return output_path


if __name__ == "__main__":
    print("Editor module loaded. Use assemble_video() or add_text_overlay() to process videos.")
