
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


# Locate project root and load environment variables
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def generate_json(system_prompt, user_input):
    """
    Send a prompt to Gemini and return its JSON response
    as a Python dictionary.
    """

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Check your .env file."
        )

    if not model:
        raise ValueError(
            "GEMINI_MODEL is missing. Check your .env file."
        )

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=user_input,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(
                thinking_level="LOW"
            )
        )
    )

    if not response.text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    try:
        return json.loads(response.text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini did not return valid JSON."
        ) from error
