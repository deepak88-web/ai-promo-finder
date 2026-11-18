import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

REQUEST_TIMEOUT = 60.0
MAX_ATTEMPTS = 3


def sanitize_error(error: Exception, api_key: str | None) -> str:
    msg = str(error)
    if api_key and len(api_key) > 5 and api_key in msg:
        msg = msg.replace(api_key, "[REDACTED_API_KEY]")
    return msg


def generate_json(system_prompt, user_input, api_key=None, model=None, base_url=None, **kwargs):
    """
    Send prompt to any OpenAI-compatible provider (OpenAI, DeepSeek, vLLM, Ollama, etc.)
    and return parsed JSON response.
    """
    from openai import OpenAI

    resolved_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
    resolved_model = model or os.getenv("OPENAI_MODEL") or os.getenv("CUSTOM_MODEL", "gpt-4o-mini")
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("CUSTOM_BASE_URL")

    if not resolved_key:
        raise ValueError("API key is missing for OpenAI-compatible provider. Enter it in the UI or set OPENAI_API_KEY / CUSTOM_API_KEY.")

    client = OpenAI(
        api_key=resolved_key,
        base_url=resolved_base_url,
        timeout=REQUEST_TIMEOUT,
    )

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("OpenAI-compatible provider returned an empty response.")

            return json.loads(content)

        except Exception as exc:
            last_error = exc
            err_text = sanitize_error(exc, resolved_key)
            err_lower = err_text.lower()

            # Fast fail on authentication error
            if "401" in err_lower or "unauthorized" in err_lower or "invalid api key" in err_lower:
                raise RuntimeError(f"Authentication failed: {err_text}") from None

            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"Request failed after {MAX_ATTEMPTS} attempts: {err_text}") from None

            wait_seconds = 2 ** (attempt - 1)
            time.sleep(wait_seconds)

    raise RuntimeError(f"OpenAI-compatible request failed: {sanitize_error(last_error, resolved_key)}")
