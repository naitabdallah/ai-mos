"""Script generation module using AWS Bedrock.

Generates a structured YouTube script from research output, calls Claude 3.5
Sonnet via AWS Bedrock, and returns a JSON-structured script ready for the
downstream audio and video pipeline stages.
"""

import json
import os

from config.config import bedrock_client, settings

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "script_prompt.txt")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
SCRIPT_OUTPUT_PATH = os.path.join(ASSETS_DIR, "script_output.json")


def _load_prompt_template() -> str:
    """Load the script prompt template from disk."""
    with open(PROMPT_PATH, "r") as f:
        return f.read()


def generate_script(topic_dict: dict) -> dict:
    """Generate a structured YouTube script from research output.

    Args:
        topic_dict: Dictionary produced by research.py containing at minimum
            ``topic``, ``angle``, ``target_audience``, and ``key_points``.

    Returns:
        A dict matching the structured JSON script schema (title, description,
        tags, hook, sections, cta, total_duration_estimate).

    Raises:
        RuntimeError: If the Bedrock client is not initialised.
        ValueError: If the model response cannot be parsed as valid JSON.
        KeyError: If required keys are missing from *topic_dict*.
    """
    if bedrock_client is None:
        raise RuntimeError(
            "AWS Bedrock client is not initialised. "
            "Check your AWS credentials and config."
        )

    template = _load_prompt_template()

    # Format key_points as a readable string if it's a list
    key_points = topic_dict.get("key_points", [])
    if isinstance(key_points, list):
        key_points_str = "\n".join(f"- {point}" for point in key_points)
    else:
        key_points_str = str(key_points)

    prompt = template.format(
        topic=topic_dict["topic"],
        angle=topic_dict.get("angle", "general overview"),
        target_audience=topic_dict.get("target_audience", "general audience"),
        key_points=key_points_str,
    )

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
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
    raw_text = result["content"][0]["text"]

    # Strip markdown fences if the model wraps the JSON anyway
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -len("```")]
    cleaned = cleaned.strip()

    try:
        script = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse model response as JSON: {exc}\n"
            f"Raw response (first 500 chars): {raw_text[:500]}"
        ) from exc

    # Basic validation of expected top-level keys
    required_keys = {"title", "hook", "sections", "cta"}
    missing = required_keys - set(script.keys())
    if missing:
        raise ValueError(
            f"Model response is missing required keys: {missing}"
        )

    return script


def save_script(script: dict) -> str:
    """Save the generated script to disk as JSON.

    Args:
        script: The structured script dictionary.

    Returns:
        The file path where the script was saved.
    """
    os.makedirs(ASSETS_DIR, exist_ok=True)

    with open(SCRIPT_OUTPUT_PATH, "w") as f:
        json.dump(script, f, indent=2)

    print(f"Script saved to {SCRIPT_OUTPUT_PATH}")
    return SCRIPT_OUTPUT_PATH


def run(topic_dict: dict) -> dict:
    """High-level entry point: generate a script and persist it.

    Args:
        topic_dict: Research output dictionary.

    Returns:
        The structured script dictionary.
    """
    script = generate_script(topic_dict)
    save_script(script)
    return script


if __name__ == "__main__":
    sample_topic = {
        "topic": "How AI is changing music production",
        "angle": "Practical tools musicians can use today",
        "target_audience": "Independent musicians and producers",
        "key_points": [
            "AI-powered mastering services",
            "Stem separation technology",
            "AI melody and chord generators",
            "Ethical concerns around AI-generated music",
        ],
    }
    result = run(sample_topic)
    print(json.dumps(result, indent=2))
