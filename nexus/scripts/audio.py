"""Audio generation module for the Nexus YouTube automation pipeline.

Converts a structured script dict into voiceover audio using ElevenLabs
text-to-speech, then concatenates the segments (with optional background
music) via ffmpeg-python.
"""

import os
import tempfile

import ffmpeg

from config.config import elevenlabs_client, settings

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
BG_MUSIC_PATH = os.path.join(ASSETS_DIR, "background_music.mp3")
FINAL_OUTPUT = os.path.join(AUDIO_DIR, "final_voiceover.mp3")

# Duration (in seconds) of silence inserted between segments
SILENCE_GAP = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_segments(script: dict) -> list[str]:
    """Pull ordered text segments from a script dict.

    Expected script structure::

        {
            "hook": "...",
            "sections": [{"title": "...", "content": "..."}, ...],
            "cta": "..."
        }

    Returns a flat list of non-empty text strings.
    """
    segments: list[str] = []

    hook = script.get("hook", "")
    if hook:
        segments.append(hook)

    for section in script.get("sections", []):
        content = section.get("content", "")
        if content:
            segments.append(content)

    cta = script.get("cta", "")
    if cta:
        segments.append(cta)

    return segments


def _generate_silence(duration: float, path: str) -> str:
    """Create a silent MP3 file of *duration* seconds at *path*."""
    (
        ffmpeg
        .input("anullsrc=r=44100:cl=stereo", f="lavfi", t=duration)
        .output(path, acodec="libmp3lame", ar=44100, ac=2)
        .overwrite_output()
        .run(quiet=True)
    )
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_voiceover(script: dict) -> list:
    """Convert each script segment to speech via ElevenLabs.

    Parameters
    ----------
    script:
        Structured script dict with ``hook``, ``sections``, and ``cta``.

    Returns
    -------
    list[str]
        Paths to the generated ``assets/audio/segment_<i>.mp3`` files.
    """
    if elevenlabs_client is None:
        raise RuntimeError(
            "ElevenLabs client is not initialised. "
            "Set ELEVENLABS_API_KEY in your .env file."
        )

    voice_id = settings.get("ELEVENLABS_VOICE_ID", "")
    if not voice_id:
        raise RuntimeError("ELEVENLABS_VOICE_ID is not set in your .env file.")

    segments = _extract_segments(script)
    if not segments:
        raise ValueError("Script produced no text segments to convert.")

    os.makedirs(AUDIO_DIR, exist_ok=True)
    audio_paths: list[str] = []

    for index, text in enumerate(segments):
        out_path = os.path.join(AUDIO_DIR, f"segment_{index}.mp3")
        print(f"[audio] Generating segment {index} ({len(text)} chars)...")

        try:
            audio_iter = elevenlabs_client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            )
            with open(out_path, "wb") as f:
                for chunk in audio_iter:
                    f.write(chunk)
        except Exception as exc:
            raise RuntimeError(
                f"ElevenLabs TTS failed on segment {index}: {exc}"
            ) from exc

        audio_paths.append(out_path)

    print(f"[audio] Generated {len(audio_paths)} audio segments")
    return audio_paths


def combine_audio(audio_files: list) -> str:
    """Concatenate segment MP3s with silence gaps and optional background music.

    A 0.5-second silence is inserted between each segment for natural
    pacing.  If ``assets/background_music.mp3`` exists it is mixed in at
    10 % volume underneath the voiceover.

    Parameters
    ----------
    audio_files:
        Ordered list of segment MP3 file paths.

    Returns
    -------
    str
        Path to ``assets/audio/final_voiceover.mp3``.
    """
    if not audio_files:
        raise ValueError("No audio files provided to combine.")

    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Build a concat list interleaving segments with silence
    concat_entries: list[str] = []
    silence_path = os.path.join(AUDIO_DIR, "_silence.mp3")
    _generate_silence(SILENCE_GAP, silence_path)

    for i, path in enumerate(audio_files):
        concat_entries.append(path)
        if i < len(audio_files) - 1:
            concat_entries.append(silence_path)

    # Write ffmpeg concat demuxer file
    concat_list_path = os.path.join(AUDIO_DIR, "_concat_list.txt")
    with open(concat_list_path, "w") as f:
        for entry in concat_entries:
            # Paths need to be absolute for the concat demuxer
            abs_path = os.path.abspath(entry)
            f.write(f"file '{abs_path}'\n")

    # Concatenate all segments + silences into a single file
    concat_tmp = os.path.join(AUDIO_DIR, "_concat_tmp.mp3")
    try:
        (
            ffmpeg
            .input(concat_list_path, f="concat", safe=0)
            .output(concat_tmp, acodec="libmp3lame", ar=44100, ac=2)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        raise RuntimeError(f"ffmpeg concat failed: {exc}") from exc

    # Mix in background music if available
    if os.path.isfile(BG_MUSIC_PATH):
        print("[audio] Mixing in background music at 10% volume...")
        try:
            voice = ffmpeg.input(concat_tmp)
            music = ffmpeg.input(BG_MUSIC_PATH, stream_loop=-1)
            # Trim music to match voiceover length, reduce to 10% volume
            music_quiet = music.filter("volume", 0.1)
            (
                ffmpeg
                .filter([voice, music_quiet], "amix", inputs=2, duration="first")
                .output(FINAL_OUTPUT, acodec="libmp3lame", ar=44100, ac=2)
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as exc:
            raise RuntimeError(f"ffmpeg background mix failed: {exc}") from exc
    else:
        # No background music -- just rename the concat output
        os.replace(concat_tmp, FINAL_OUTPUT)

    # Clean up temp files
    for tmp in (silence_path, concat_list_path, concat_tmp):
        if os.path.exists(tmp):
            os.remove(tmp)

    print(f"[audio] Final voiceover saved to {FINAL_OUTPUT}")
    return FINAL_OUTPUT


def run(script: dict) -> str:
    """Run the full audio step: generate segments then combine.

    Parameters
    ----------
    script:
        Structured script dict (hook, sections, cta).

    Returns
    -------
    str
        Path to the final combined audio file.
    """
    audio_files = generate_voiceover(script)
    final_path = combine_audio(audio_files)
    return final_path


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python audio.py <script.json>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        script_data = json.load(f)

    result = run(script_data)
    print(f"Done: {result}")
