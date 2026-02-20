"""Audio generation module using ElevenLabs text-to-speech."""

import os

from config.config import elevenlabs_client, settings

AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "audio")


def generate_voiceover(text: str, output_filename: str = "voiceover.mp3") -> str:
    """Generate a voiceover audio file from text using ElevenLabs.

    Args:
        text: The script text to convert to speech.
        output_filename: Name of the output audio file.

    Returns:
        The path to the generated audio file.
    """
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(AUDIO_OUTPUT_DIR, output_filename)

    audio = elevenlabs_client.text_to_speech.convert(
        voice_id=settings["ELEVENLABS_VOICE_ID"],
        text=text,
        model_id="eleven_multilingual_v2",
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    print(f"Voiceover saved to {output_path}")
    return output_path


if __name__ == "__main__":
    sample_text = "This is a test of the voiceover generation system."
    generate_voiceover(sample_text, "test_voiceover.mp3")
