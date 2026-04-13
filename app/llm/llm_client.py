
from __future__ import annotations

import os

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

def run_llm(prompt: str, model: str = "gpt-4.1-mini") -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in the environment")

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
    )
    return response.output_text
