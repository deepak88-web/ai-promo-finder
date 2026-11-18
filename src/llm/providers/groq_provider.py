import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

REQUEST_TIMEOUT = 60.0
MAX_ATTEMPTS = 3
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def sanitize_error(error: Exception, api_key: str | None) -> str:
    msg = str(error)
    if api_key and len(api_key) > 5 and api_key in msg:
        msg = msg.replace(api_key, "[REDACTED_API_KEY]")
    return msg


def generate_json(system_prompt, user_input, api_key=None, model=None, base_url=None, **kwargs):
    """
    Send prompt to Groq and return parsed JSON object.
    Includes timeouts, exponential backoff retries on rate limits, and key sanitization.
    """
    from groq import Groq

    resolved_key = api_key or os.getenv("GROQ_API_KEY")
    resolved_model = model or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL

    if not resolved_key:
        raise ValueError("GROQ_API_KEY is missing. Enter it in the UI or check your .env file.")

    client = Groq(
        api_key=resolved_key,
        timeout=REQUEST_TIMEOUT,
    )

    combined_prompt = f"{system_prompt}\n\nUSER INPUT:\n{user_input}"

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                messages=[
                    {"role": "user", "content": combined_prompt}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=4096,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Groq returned an empty response.")

            try:
                return json.loads(content)
            except json.JSONDecodeError as err:
                raise ValueError(f"Groq did not return valid JSON: {content[:200]}") from err

        except Exception as exc:
            last_error = exc
            err_text = sanitize_error(exc, resolved_key)
            err_lower = err_text.lower()

            if "401" in err_lower or "unauthorized" in err_lower or "invalid api key" in err_lower:
                raise RuntimeError(f"Groq authentication failed: {err_text}") from None

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"Groq request failed after {MAX_ATTEMPTS} attempts: {err_text}") from None

            wait_seconds = 2 ** (attempt - 1) * 2
            time.sleep(wait_seconds)

    raise RuntimeError(f"Groq request failed: {sanitize_error(last_error, resolved_key)}")
