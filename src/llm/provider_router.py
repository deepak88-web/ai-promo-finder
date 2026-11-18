import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_provider(layer, provider_override=None):
    """
    Return the configured provider name and generate_json function.

    Supported providers: groq, gemini, openai_compatible (or custom/openai), mock.
    """
    layer = layer.lower()
    valid_layers = {"layer1", "layer2", "promo_evaluation", "semantic_verifier"}
    if layer not in valid_layers:
        raise ValueError(
            f"Layer must be one of {valid_layers}, got '{layer}'."
        )

    if provider_override:
        provider_name = str(provider_override).strip().lower()
    else:
        provider_key = f"{layer.upper()}_PROVIDER"
        provider_name = os.getenv(
            provider_key,
            "gemini" if layer in {"promo_evaluation", "semantic_verifier"} else "groq"
        ).strip().lower()

    # Normalization aliases
    if provider_name in {"openai", "custom", "openai_compatible", "openai-compatible"}:
        provider_name = "openai_compatible"
    elif provider_name in {"mock", "fake", "test"}:
        provider_name = "mock"

    if provider_name == "groq":
        from src.llm.providers.groq_provider import generate_json
    elif provider_name == "gemini":
        from src.llm.providers.gemini_provider import generate_json
    elif provider_name == "openai_compatible":
        from src.llm.providers.openai_compatible_provider import generate_json
    elif provider_name == "mock":
        from src.llm.providers.mock_provider import generate_json
    else:
        raise ValueError(
            f"Unsupported provider '{provider_name}' for {layer}. "
            "Choose 'groq', 'gemini', 'openai_compatible', or 'mock'."
        )

    return provider_name, generate_json
