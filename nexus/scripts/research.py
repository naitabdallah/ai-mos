"""Research module for gathering topic information via AWS Bedrock."""

import json
import os

from config.config import bedrock_client, settings


def load_research_prompt(topic: str, niche: str = "general") -> str:
    """Load the research prompt template and fill in variables."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "research_prompt.txt")
    with open(prompt_path, "r") as f:
        template = f.read()
    return template.format(topic=topic, niche=niche)


def research_topic(topic: str, niche: str = "general") -> str:
    """Send a research request to AWS Bedrock and return the response."""
    prompt = load_research_prompt(topic, niche)

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
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
    print(research_topic(topic))
