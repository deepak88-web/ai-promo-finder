import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

REQUEST_TIMEOUT = 120_000  # 120 seconds in milliseconds
MAX_ATTEMPTS = 3
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

RETRYABLE_STATUS_CODES = {
    408,
    429,
    500,
    502,
    503,
    504,
}


def sanitize_error(error: Exception, api_key: str | None) -> str:
    msg = str(error)
    if api_key and len(api_key) > 5 and api_key in msg:
        msg = msg.replace(api_key, "[REDACTED_API_KEY]")
    return msg


def is_retryable_error(error):
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status_code in RETRYABLE_STATUS_CODES:
        return True

    error_name = type(error).__name__.lower()
    retryable_error_names = (
        "timeout",
        "connection",
        "temporarily",
        "serviceunavailable",
    )
    return any(name in error_name for name in retryable_error_names)


def generate_json(system_prompt, user_input, api_key=None, model=None, base_url=None, **kwargs):
    """
    Send prompt to Gemini and return parsed JSON response.
    Includes request timeout, controlled retries, key sanitization, and quota guards.
    """
    resolved_key = api_key or os.getenv("GEMINI_API_KEY")
    resolved_model = model or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL

    if not resolved_key:
        raise ValueError("GEMINI_API_KEY is missing. Enter it in the UI or check your .env file.")

    client = genai.Client(
        api_key=resolved_key,
        http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT
        ),
    )

    # Only attach thinking config if specifically requested
    thinking_cfg = None
    if kwargs.get("enable_thinking") or "thinking" in resolved_model.lower():
        thinking_cfg = types.ThinkingConfig(thinking_level="LOW")

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            gen_config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                max_output_tokens=8192,
            )
            if thinking_cfg:
                gen_config.thinking_config = thinking_cfg

            response = client.models.generate_content(
                model=resolved_model,
                contents=user_input,
                config=gen_config,
            )

            if not response.text:
                raise ValueError("Gemini returned an empty response.")

            try:
                return json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Gemini did not return valid JSON: {response.text[:200]}") from exc

        except Exception as exc:
            last_error = exc
            err_text = sanitize_error(exc, resolved_key)
            err_lower = err_text.lower()

            # Stop immediately on daily quota exhaustion
            if "429" in err_lower and any(p in err_lower for p in ["requests per day", "request per day", "daily quota"]):
                raise RuntimeError(
                    "Gemini daily API request quota exhausted. No further retries attempted."
                ) from None

            # Fast fail on invalid API key
            if "400" in err_lower and "api_key_invalid" in err_lower or "401" in err_lower or "unauthorized" in err_lower:
                raise RuntimeError(f"Gemini authentication failed: {err_text}") from None

            if not is_retryable_error(exc):
                raise RuntimeError(f"Gemini error: {err_text}") from None

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"Gemini request failed after {MAX_ATTEMPTS} attempts: {err_text}") from None

            wait_seconds = 5 * (2 ** (attempt - 1))
            time.sleep(wait_seconds)

    raise RuntimeError(f"Gemini request failed: {sanitize_error(last_error, resolved_key)}")
