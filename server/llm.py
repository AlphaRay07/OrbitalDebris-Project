import os

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def ask(prompt: str, tools=None, model: str = "claude-sonnet-5") -> anthropic.types.Message:
    return client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        tools=tools or [],
    )
