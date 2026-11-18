
"""
Provider-routed complete promo evaluator for AI Promo Finder.

Evaluates structurally validated promos for:
- Opening hook
- Standalone coherence
- Narrative flow
- Emotional impact
- Cliffhanger effectiveness
- Promotional appeal

Evaluations are cached using both:
1. Promo content
2. Evaluation prompt fingerprint

A changed evaluation prompt automatically triggers reevaluation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

DEFAULT_MODEL = os.getenv(
    "PROMO_EVALUATION_MODEL",
    "gemini-3.5-flash-lite",
)
DEFAULT_PROVIDER = os.getenv("PROMO_EVALUATION_PROVIDER", "gemini").strip().lower()

DEFAULT_BATCH_SIZE = 3
DEFAULT_MAX_RETRIES = 3

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "llm"
    / "prompts"
    / "promo_evaluation.txt"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "raw"
    / "expanded"
    / "promo_evaluation.json"
)

VALIDATION_INPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "raw"
    / "expanded"
    / "promo_validation_results.json"
)

BACKUP_DIRECTORY = (
    PROJECT_ROOT
    / "outputs"
    / "backups"
)

DECISIONS = {"recommend", "revise", "reject"}

SCORE_FIELDS = [
    "opening_hook",
    "standalone_coherence",
    "narrative_flow",
    "emotional_impact",
    "cliffhanger_effectiveness",
    "promotional_appeal",
]

# The overall score is calculated deterministically.
SCORE_WEIGHTS = {
    "opening_hook": 0.20,
    "standalone_coherence": 0.20,
    "narrative_flow": 0.15,
    "emotional_impact": 0.15,
    "cliffhanger_effectiveness": 0.20,
    "promotional_appeal": 0.10,
}


# ============================================================
# GEMINI RESPONSE SCHEMA
# ============================================================

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "promo_id": {"type": "string"},

                    "opening_hook": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },
                    "standalone_coherence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },
                    "narrative_flow": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },
                    "emotional_impact": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },
                    "cliffhanger_effectiveness": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },
                    "promotional_appeal": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },

                    "overall_score": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                    },

                    "hook_explanation": {"type": "string"},
                    "coherence_explanation": {"type": "string"},
                    "flow_explanation": {"type": "string"},
                    "cliffhanger_explanation": {"type": "string"},
                    "one_line_pitch": {"type": "string"},

                    "strengths": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "weaknesses": {
                        "type": "array",
                        "items": {"type": "string"},
                    },

                    "improvement_suggestion": {
                        "type": "string",
                    },

                    "decision": {
                        "type": "string",
                        "enum": [
                            "recommend",
                            "revise",
                            "reject",
                        ],
                    },
                },
                "required": [
                    "promo_id",
                    "opening_hook",
                    "standalone_coherence",
                    "narrative_flow",
                    "emotional_impact",
                    "cliffhanger_effectiveness",
                    "promotional_appeal",
                    "overall_score",
                    "hook_explanation",
                    "coherence_explanation",
                    "flow_explanation",
                    "cliffhanger_explanation",
                    "one_line_pitch",
                    "strengths",
                    "weaknesses",
                    "improvement_suggestion",
                    "decision",
                ],
            },
        }
    },
    "required": ["evaluations"],
}


# ============================================================
# PROMPT LOADING AND FINGERPRINTING
# ============================================================

def load_evaluation_prompt() -> str:
    """Load the evaluation instructions from the prompt file."""

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Evaluation prompt not found: {PROMPT_PATH}"
        )

    prompt = PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()

    if not prompt:
        raise ValueError("The evaluation prompt file is empty.")

    return prompt


def calculate_prompt_hash(prompt: str) -> str:
    """Generate a fingerprint for the current evaluation prompt."""

    return hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()


def calculate_evaluation_fingerprint(
    prompt: str,
    provider: str,
    model: str,
) -> str:
    """Fingerprint the prompt and provider configuration used for scoring."""
    return calculate_prompt_hash(f"{prompt}\nprovider={provider}\nmodel={model}")


# ============================================================
# PREPARE PROMO INPUT
# ============================================================

def compact_source_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    """Keep only relevant screenplay evidence."""

    return {
        "event_id": event.get("event_id"),
        "episode": event.get("episode"),
        "start_time": event.get("start_time"),
        "end_time": event.get("end_time"),
        "type": event.get("type"),
        "speaker": event.get("speaker"),
        "tone": event.get("tone"),
        "text": str(event.get("text") or "")[:2000],
    }


def prepare_segment(
    segment: dict[str, Any],
) -> dict[str, Any]:
    """Prepare one promo segment for Gemini."""

    source_events = segment.get("source_events", [])

    if not isinstance(source_events, list):
        source_events = []

    return {
        "segment_order": segment.get("segment_order"),
        "episode": segment.get("episode"),
        "start_time": segment.get("start_time"),
        "end_time": segment.get("end_time"),
        "duration": segment.get("duration"),
        "event_ids": segment.get("event_ids", []),
        "source_events": [
            compact_source_event(event)
            for event in source_events
            if isinstance(event, dict)
        ],
    }


def prepare_promo_for_evaluation(
    promo: dict[str, Any],
) -> dict[str, Any]:
    """Create a compact, grounded payload for one promo."""

    return {
        "promo_id": promo.get("promo_id"),
        "construction_type": promo.get("construction_type"),
        "segment_count": promo.get("segment_count"),
        "episodes": promo.get("episodes", []),
        "total_duration": (
            promo.get("actual_duration")
            or promo.get("total_duration")
        ),
        "hook_evidence": promo.get("hook", {}),
        "cliffhanger_evidence": promo.get("cliffhanger", {}),
        "segments": [
            prepare_segment(segment)
            for segment in promo.get("segments", [])
            if isinstance(segment, dict)
        ],
    }


# ============================================================
# BUILD GEMINI REQUEST
# ============================================================

def build_batch_prompt(
    batch: list[dict[str, Any]],
    system_prompt: str,
) -> str:
    """Build one request containing multiple promos."""

    payload = json.dumps(
        batch,
        ensure_ascii=False,
        indent=2,
    )

    return (
        system_prompt
        + "\n\nEvaluate the following promos.\n"
        + "Return exactly one evaluation for every promo_id.\n"
        + "Follow the supplied evaluation criteria and JSON schema.\n\n"
        + payload
    )


# ============================================================
# SCORE CALCULATION
# ============================================================

def calculate_overall_score(
    evaluation: dict[str, Any],
) -> float:
    """
    Calculate the weighted overall score.

    Weights:
    Hook                 20%
    Standalone coherence 20%
    Narrative flow      15%
    Emotional impact    15%
    Cliffhanger         20%
    Promotional appeal  10%
    """

    weighted_score = sum(
        float(evaluation[field]) * weight
        for field, weight in SCORE_WEIGHTS.items()
    )

    return round(weighted_score, 1)


# ============================================================
# RESPONSE VALIDATION
# ============================================================

def validate_evaluation_response(
    response_text: str,
    expected_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """Validate Gemini's structured response."""

    try:
        payload = json.loads(response_text)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Gemini returned invalid JSON."
        ) from exc

    evaluations = payload.get("evaluations")

    if not isinstance(evaluations, list):
        raise ValueError(
            "Gemini response is missing the evaluations list."
        )

    validated = {}

    for item in evaluations:

        if not isinstance(item, dict):
            raise ValueError(
                "An evaluation item is not an object."
            )

        promo_id = item.get("promo_id")

        if promo_id not in expected_ids:
            raise ValueError(
                f"Unexpected promo_id returned: {promo_id}"
            )

        if promo_id in validated:
            raise ValueError(
                f"Duplicate evaluation returned for {promo_id}"
            )

        # Validate all individual scores.
        for field in SCORE_FIELDS:

            score = item.get(field)

            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 10
            ):
                raise ValueError(
                    f"Invalid {field} score for {promo_id}"
                )

        # Validate explanations and text fields.
        text_fields = [
            "hook_explanation",
            "coherence_explanation",
            "flow_explanation",
            "cliffhanger_explanation",
            "one_line_pitch",
            "improvement_suggestion",
        ]

        for field in text_fields:

            if not isinstance(item.get(field), str):
                raise ValueError(
                    f"Missing or invalid {field} for {promo_id}"
                )

        # Validate strengths and weaknesses.
        for field in ["strengths", "weaknesses"]:

            if (
                not isinstance(item.get(field), list)
                or not all(
                    isinstance(value, str)
                    for value in item[field]
                )
            ):
                raise ValueError(
                    f"Invalid {field} for {promo_id}"
                )

        # Validate decision.
        if item.get("decision") not in DECISIONS:
            raise ValueError(
                f"Invalid decision for {promo_id}"
            )

        # Do not trust Gemini's arithmetic.
        # Calculate the overall score using fixed weights.
        item["overall_score"] = calculate_overall_score(item)

        validated[promo_id] = item

    missing = expected_ids - set(validated)

    if missing:
        raise ValueError(
            "Gemini omitted promo IDs: "
            + ", ".join(sorted(missing))
        )

    return validated


# ============================================================
# EVALUATE ONE BATCH
# ============================================================

def evaluate_promo_batch(
    client: genai.Client | None,
    batch: list[dict[str, Any]],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    provider: str = DEFAULT_PROVIDER,
) -> dict[str, dict[str, Any]]:
    """Evaluate one batch through Gemini's schema API or the provider router."""

    expected_ids = {
        item["promo_id"]
        for item in batch
    }

    prompt = build_batch_prompt(
        batch,
        system_prompt,
    )

    last_error = None

    for attempt in range(max_retries):

        try:
            if provider == "gemini":
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": 0.2,
                        "response_mime_type": "application/json",
                        "response_schema": RESPONSE_SCHEMA,
                    },
                )
                response_text = getattr(response, "text", None)
            else:
                from src.llm.provider_router import get_provider
                _, generate_json = get_provider("promo_evaluation")
                payload = {
                    "promos": batch,
                    "required_schema": RESPONSE_SCHEMA,
                    "required_output": {
                        "evaluations": "one evaluation per promo_id, using exactly the fields in the supplied schema"
                    },
                }
                result = generate_json(
                    system_prompt,
                    json.dumps(payload, ensure_ascii=False, indent=2),
                )
                response_text = json.dumps(result, ensure_ascii=False)

            if not response_text:
                raise ValueError(f"{provider.title()} returned an empty response.")

            return validate_evaluation_response(
                response_text,
                expected_ids,
            )

        except Exception as exc:

            last_error = exc

            print(
                f"Gemini evaluation attempt "
                f"{attempt + 1}/{max_retries} failed: {exc}"
            )

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Promo evaluation failed after {max_retries} attempts."
    ) from last_error


# ============================================================
# EVALUATE ALL PROMOS
# ============================================================

def evaluate_promos(
    validation_results: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    provider: str | None = None,
) -> dict[str, Any]:
    """Evaluate structurally valid promos."""

    if batch_size < 1:
        raise ValueError(
            "batch_size must be at least 1."
        )

    resolved_provider = (provider or DEFAULT_PROVIDER).strip().lower()
    if resolved_provider not in {"gemini", "groq"}:
        raise ValueError("PROMO_EVALUATION_PROVIDER must be 'gemini' or 'groq'.")
    api_env_name = "GEMINI_API_KEY" if resolved_provider == "gemini" else "GROQ_API_KEY"
    resolved_api_key = api_key or os.getenv(api_env_name)

    if not resolved_api_key:
        raise EnvironmentError(
            f"{api_env_name} is missing. "
            "Check your .env file."
        )

    resolved_model = model or (
        DEFAULT_MODEL if resolved_provider == "gemini"
        else os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    )

    system_prompt = load_evaluation_prompt()
    prompt_hash = calculate_evaluation_fingerprint(
        system_prompt, resolved_provider, resolved_model
    )

    valid_promos = validation_results.get(
        "valid_promos",
        [],
    )

    invalid_promos = validation_results.get(
        "invalid_promos",
        [],
    )

    if not isinstance(valid_promos, list):
        raise ValueError("valid_promos must be a list.")

    print("\n========== PROMO EVALUATOR ==========")
    print(f"Valid promos received: {len(valid_promos)}")
    print(f"Invalid promos skipped: {len(invalid_promos)}")
    print(f"Batch size: {batch_size}")
    print(f"Provider/model: {resolved_provider}/{resolved_model}")
    print(f"Prompt fingerprint: {prompt_hash[:16]}")
    print("=====================================")

    if not valid_promos:
        raise ValueError("No valid promos were supplied for evaluation.")

    client = (
        genai.Client(api_key=resolved_api_key)
        if resolved_provider == "gemini" else None
    )

    prepared_promos = [
        prepare_promo_for_evaluation(promo)
        for promo in valid_promos
    ]

    evaluations_by_id = {}

    total_batches = (
        len(prepared_promos) + batch_size - 1
    ) // batch_size

    for batch_number, start in enumerate(
        range(0, len(prepared_promos), batch_size),
        start=1,
    ):

        batch = prepared_promos[
            start:start + batch_size
        ]

        print(
            f"\nEvaluating batch {batch_number}/{total_batches} "
            f"({len(batch)} promos)..."
        )

        batch_results = evaluate_promo_batch(
            client=client,
            batch=batch,
            system_prompt=system_prompt,
            model=resolved_model,
            max_retries=max_retries,
            provider=resolved_provider,
        )

        evaluations_by_id.update(batch_results)

    evaluated_promos = []

    for promo in valid_promos:

        promo_id = promo.get("promo_id")
        evaluation = evaluations_by_id.get(promo_id)

        if evaluation is None:
            continue

        evaluated = dict(promo)
        evaluated["evaluation"] = evaluation
        evaluated["evaluation_status"] = "completed"

        evaluated_promos.append(evaluated)

    recommended = [
        promo for promo in evaluated_promos
        if promo["evaluation"]["decision"] == "recommend"
    ]

    needs_revision = [
        promo for promo in evaluated_promos
        if promo["evaluation"]["decision"] == "revise"
    ]

    rejected = [
        promo for promo in evaluated_promos
        if promo["evaluation"]["decision"] == "reject"
    ]

    evaluated_promos.sort(
        key=lambda item: item["evaluation"]["overall_score"],
        reverse=True,
    )

    statistics = {
        "total_valid_promos": len(valid_promos),
        "total_invalid_promos_skipped": len(invalid_promos),
        "total_evaluated": len(evaluated_promos),
        "recommended": len(recommended),
        "needs_revision": len(needs_revision),
        "rejected": len(rejected),
        "batch_size": batch_size,
        "total_batches": total_batches,
        "model": resolved_model,
        "provider": resolved_provider,
        "prompt_sha256": prompt_hash,
    }

    results = {
        "evaluated_promos": evaluated_promos,
        "recommended_promos": recommended,
        "promos_needing_revision": needs_revision,
        "rejected_promos": rejected,
        "structurally_invalid_promos": invalid_promos,
        "statistics": statistics,
    }

    print("\n========== EVALUATION RESULTS ==========")
    print(f"Evaluated: {statistics['total_evaluated']}")
    print(f"Recommended: {statistics['recommended']}")
    print(f"Needs revision: {statistics['needs_revision']}")
    print(f"Rejected: {statistics['rejected']}")
    print("========================================\n")

    return results


# ============================================================
# SAVE RESULTS AND BACKUP
# ============================================================

def backup_existing_results(
    output_path: Path = OUTPUT_PATH,
) -> Path | None:
    """Create a timestamped backup before replacing old results."""

    if not output_path.exists():
        return None

    BACKUP_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = (
        BACKUP_DIRECTORY
        / f"promo_evaluation_{timestamp}.json"
    )

    shutil.copy2(
        output_path,
        backup_path,
    )

    print(f"Previous evaluation backed up to: {backup_path}")

    return backup_path


def save_evaluation_results(
    results: dict[str, Any],
    output_path: str | Path = OUTPUT_PATH,
) -> None:
    """Save complete evaluation results as JSON."""

    destination = Path(output_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = destination.with_suffix(".tmp")

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
        )

    # Replace output only after successful JSON serialization.
    temporary_path.replace(destination)

    print(
        f"Evaluation results saved to: {destination}"
    )


# ============================================================
# PRINT TOP PROMOS
# ============================================================

def print_evaluation_summary(
    results: dict[str, Any],
    limit: int = 15,
) -> None:
    """Print the highest-scoring evaluated promos."""

    print("\n========== TOP EVALUATED PROMOS ==========")

    for rank, promo in enumerate(
        results.get("evaluated_promos", [])[:limit],
        start=1,
    ):

        evaluation = promo["evaluation"]

        print(
            f"\nRank {rank}: {promo.get('promo_id')}"
        )

        print(
            f"Overall score: "
            f"{evaluation['overall_score']}/10"
        )

        print(
            f"Decision: {evaluation['decision']}"
        )

        print(
            f"Duration: {promo.get('actual_duration')} seconds"
        )

        print(
            f"Pitch: {evaluation['one_line_pitch']}"
        )

        print(
            f"Strengths: {evaluation['strengths']}"
        )

        print(
            f"Weaknesses: {evaluation['weaknesses']}"
        )

    print("\n===========================================")


# ============================================================
# LOAD PREVIOUS EVALUATIONS
# ============================================================

def load_previous_evaluations() -> tuple[
    dict[str, dict[str, Any]],
    str | None,
]:
    """Load previous results and their prompt fingerprint."""

    if not OUTPUT_PATH.exists():
        return {}, None

    try:
        with OUTPUT_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            previous_results = json.load(file)

    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"Could not load previous evaluations: {exc}"
        )
        return {}, None

    previous_evaluations = {}

    for item in previous_results.get(
        "evaluated_promos",
        [],
    ):

        promo_id = item.get("promo_id")
        evaluation = item.get("evaluation")

        if promo_id and isinstance(evaluation, dict):
            previous_evaluations[promo_id] = item

    previous_hash = (
        previous_results
        .get("statistics", {})
        .get("prompt_sha256")
    )

    return previous_evaluations, previous_hash


# ============================================================
# STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # 1. Load the latest structurally validated promos.
    # --------------------------------------------------------

    if not VALIDATION_INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Validation results not found: {VALIDATION_INPUT_PATH}"
        )

    with VALIDATION_INPUT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        validation_results = json.load(file)

    valid_promos = validation_results.get(
        "valid_promos",
        [],
    )

    invalid_promos = validation_results.get(
        "invalid_promos",
        [],
    )

    if not isinstance(valid_promos, list):
        raise ValueError("valid_promos must be a list.")

    print("\n========== EVALUATION INPUT ==========")
    print(f"Validated promos loaded: {len(valid_promos)}")
    print(f"Invalid promos: {len(invalid_promos)}")
    print("======================================")

    # --------------------------------------------------------
    # 2. Load the current evaluation prompt and its hash.
    # --------------------------------------------------------

    current_prompt = load_evaluation_prompt()
    current_provider = DEFAULT_PROVIDER
    current_model = (
        DEFAULT_MODEL if current_provider == "gemini"
        else os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    )
    current_prompt_hash = calculate_evaluation_fingerprint(
        current_prompt, current_provider, current_model
    )

    print(
        f"\nCurrent prompt fingerprint: "
        f"{current_prompt_hash[:16]}"
    )

    # --------------------------------------------------------
    # 3. Load previous evaluations.
    # --------------------------------------------------------

    previous_evaluations, previous_prompt_hash = (
        load_previous_evaluations()
    )

    # --------------------------------------------------------
    # 4. Decide whether previous evaluations can be reused.
    # --------------------------------------------------------

    reused_promos = []
    pending_promos = []

    prompt_is_unchanged = (
        previous_prompt_hash == current_prompt_hash
    )

    if prompt_is_unchanged:
        print(
            "\nEvaluation prompt unchanged. "
            "Matching previous evaluations may be reused."
        )
    else:
        print(
            "\nEvaluation prompt has changed or no matching "
            "prompt fingerprint exists."
        )
        print(
            "Previous evaluations will NOT be reused."
        )

    for promo in valid_promos:

        promo_id = promo.get("promo_id")
        previous_item = previous_evaluations.get(promo_id)

        # Reuse is allowed only if the prompt AND promo content
        # are both unchanged.
        if prompt_is_unchanged and previous_item:

            current_payload = prepare_promo_for_evaluation(
                promo
            )

            previous_payload = prepare_promo_for_evaluation(
                previous_item
            )

            if current_payload == previous_payload:

                reused_item = dict(promo)

                reused_item["evaluation"] = (
                    previous_item["evaluation"]
                )

                reused_item["evaluation_status"] = "completed"

                reused_promos.append(reused_item)
                continue

        pending_promos.append(promo)

    print("\n========== EVALUATION PLAN ==========")
    print(f"Previous evaluations available: {len(previous_evaluations)}")
    print(f"Previous evaluations reused: {len(reused_promos)}")
    print(f"Promos requiring new evaluation: {len(pending_promos)}")
    print("=====================================")

    # --------------------------------------------------------
    # 5. Evaluate new or changed promos.
    # --------------------------------------------------------

    newly_evaluated = []

    if pending_promos:

        new_results = evaluate_promos(
            {
                "valid_promos": pending_promos,
                "invalid_promos": [],
            },
            batch_size=DEFAULT_BATCH_SIZE,
            provider=current_provider,
            model=current_model,
        )

        newly_evaluated = new_results["evaluated_promos"]

    else:

        print(
            "\nAll promos already have matching evaluations."
        )

    # --------------------------------------------------------
    # 6. Combine reused and newly evaluated results.
    # --------------------------------------------------------

    evaluated_promos = (
        reused_promos + newly_evaluated
    )

    evaluated_promos.sort(
        key=lambda item: item["evaluation"]["overall_score"],
        reverse=True,
    )

    recommended = [
        item for item in evaluated_promos
        if item["evaluation"]["decision"] == "recommend"
    ]

    needs_revision = [
        item for item in evaluated_promos
        if item["evaluation"]["decision"] == "revise"
    ]

    rejected = [
        item for item in evaluated_promos
        if item["evaluation"]["decision"] == "reject"
    ]

    # --------------------------------------------------------
    # 7. Create the complete evaluation result.
    # --------------------------------------------------------

    results = {
        "evaluated_promos": evaluated_promos,
        "recommended_promos": recommended,
        "promos_needing_revision": needs_revision,
        "rejected_promos": rejected,
        "structurally_invalid_promos": invalid_promos,
        "statistics": {
            "total_valid_promos": len(valid_promos),
            "total_invalid_promos_skipped": len(invalid_promos),
            "total_evaluated": len(evaluated_promos),
            "recommended": len(recommended),
            "needs_revision": len(needs_revision),
            "rejected": len(rejected),
            "reused_existing_evaluations": len(reused_promos),
            "newly_evaluated": len(newly_evaluated),
            "batch_size": DEFAULT_BATCH_SIZE,
            "total_batches": (
                (len(newly_evaluated) + DEFAULT_BATCH_SIZE - 1)
                // DEFAULT_BATCH_SIZE
            ),
            "model": current_model,
            "provider": current_provider,
            "prompt_sha256": current_prompt_hash,
        },
    }

    # --------------------------------------------------------
    # 8. Back up old results and save new results.
    # --------------------------------------------------------

    if newly_evaluated:
        backup_existing_results()

    save_evaluation_results(results)

    # --------------------------------------------------------
    # 9. Display results.
    # --------------------------------------------------------

    print_evaluation_summary(results)

    print("\n========== FINAL EVALUATION SUMMARY ==========")
    print(f"Validated promos: {len(valid_promos)}")
    print(f"Evaluated promos: {len(evaluated_promos)}")
    print(f"Reused evaluations: {len(reused_promos)}")
    print(f"New evaluations: {len(newly_evaluated)}")
    print(f"Recommended: {len(recommended)}")
    print(f"Needs revision: {len(needs_revision)}")
    print(f"Rejected: {len(rejected)}")
    print(f"Prompt fingerprint: {current_prompt_hash[:16]}")
    print("==============================================")
