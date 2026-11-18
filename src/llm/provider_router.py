
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def get_provider(layer):
    """
    Return the configured provider name and generate_json function.

    Supported providers: groq, gemini.
    """

    layer = layer.lower()

    if layer not in {"layer1", "layer2", "promo_evaluation"}:
        raise ValueError(
            "Layer must be 'layer1', 'layer2', or 'promo_evaluation'."
        )

    provider_key = f"{layer.upper()}_PROVIDER"
    provider_name = os.getenv(
        provider_key,
        "gemini" if layer == "promo_evaluation" else "groq"
    ).strip().lower()

    if provider_name == "groq":
        from src.llm.providers.groq_provider import generate_json

    elif provider_name == "gemini":
        from src.llm.providers.gemini_provider import generate_json

    else:
        raise ValueError(
            f"Unsupported provider '{provider_name}' for {layer}. "
            "Choose 'groq' or 'gemini'."
        )

    return provider_name, generate_json
