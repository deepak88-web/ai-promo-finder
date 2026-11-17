
import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


# --------------------------------------------------
# 1. Project configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(PROJECT_ROOT / ".env", override=True)

REQUEST_TIMEOUT = 120_000  # 120 seconds, in milliseconds
MAX_ATTEMPTS = 3

RETRYABLE_STATUS_CODES = {
    408,
    429,
    500,
    502,
    503,
    504
}


# --------------------------------------------------
# 2. Check whether an error can be retried
# --------------------------------------------------

def is_retryable_error(error):
    """Identify temporary API and network errors."""

    status_code = (
        getattr(error, "status_code", None)
        or getattr(error, "code", None)
    )

    if status_code in RETRYABLE_STATUS_CODES:
        return True

    error_name = type(error).__name__.lower()

    retryable_error_names = (
        "timeout",
        "connection",
        "temporarily",
        "serviceunavailable"
    )

    if any(name in error_name for name in retryable_error_names):
        return True

    return False


# --------------------------------------------------
# 3. Generate JSON using Gemini
# --------------------------------------------------

def generate_json(system_prompt, user_input):
    """
    Send a prompt to Gemini and return its JSON response
    as a Python dictionary.

    Includes request timeout and controlled retries.
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

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT
        )
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):

        try:
            print(
                f"Gemini request attempt "
                f"{attempt}/{MAX_ATTEMPTS}..."
            )

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

        
        except Exception as error:

            error_message = str(error).lower()

            # Stop immediately if the daily request quota is exhausted.
            daily_quota_exhausted = (
                "429" in error_message
                and any(
                    phrase in error_message
                    for phrase in [
                        "requests per day",
                        "request per day",
                        "perday",
                        "daily quota",
                        "daily request limit"
                    ]
                )
            )

            if daily_quota_exhausted:
                raise RuntimeError(
                    "Gemini daily API request quota exhausted. "
                    "No further retries will be attempted. "
                    "Wait for the quota reset or use an authorized "
                    "alternative API key."
                ) from error

            # Do not retry errors that are unlikely to succeed.
            if not is_retryable_error(error):
                raise

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Gemini request failed after "
                    f"{MAX_ATTEMPTS} attempts."
                ) from error

            wait_seconds = 5 * (2 ** (attempt - 1))

            print(
                f"Temporary Gemini error: {error}"
            )

            print(
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)

