"""Script generation module using AWS Bedrock."""

import json
import os

from config.config import bedrock_client, settings


def load_script_prompt(topic: str, length: str = "10", style: str = "informative") -> str:
    """Load the script prompt template and fill in variables."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "script_prompt.txt")
    with open(prompt_path, "r") as f:
        template = f.read()
    return template.format(topic=topic, length=length, style=style)


def generate_script(topic: str, research: str = "", length: str = "10", style: str = "informative") -> str:
    """Generate a YouTube script using AWS Bedrock."""
    prompt = load_script_prompt(topic, length, style)

    if research:
        prompt += f"\n\nHere is background research to incorporate:\n{research}"

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
    return result["content"][0]["text"]


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence"
    print(generate_script(topic))
