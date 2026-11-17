
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

def generate_json(system_prompt, user_input):
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from .env")

    if not model:
        raise ValueError("GROQ_MODEL is missing from .env")

    client = Groq(api_key=api_key)

    # Combine instructions and input into one message.
    # This is suitable for Groq reasoning models.
    combined_prompt = (
        f"{system_prompt}\n\n"
        f"USER INPUT:\n{user_input}"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": combined_prompt
            }
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=4096
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("Groq returned an empty response.")

    return json.loads(content)
