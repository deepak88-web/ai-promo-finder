
"""
Gemini-based complete promo evaluator for AI Promo Finder.

Evaluates structurally validated promos for hook, coherence, narrative flow,
emotional impact, cliffhanger effectiveness, and promotional appeal.
"""

from __future__ import annotations

import json
import os
import time
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
    "gemini-3.5-flash-lite"
)
DEFAULT_BATCH_SIZE = 3
DEFAULT_MAX_RETRIES = 3

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "llm"
    / "prompts"
    / "promo_evaluation.txt"
)

OUTPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "raw"
    / "promo_evaluation.json"
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

                    "improvement_suggestion": {"type": "string"},

                    "decision": {
                        "type": "string",
                        "enum": ["recommend", "revise", "reject"],
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
# PROMPT LOADING
# ============================================================

def load_evaluation_prompt() -> str:
    """Load the evaluation instructions from the prompt file."""

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Evaluation prompt not found: {PROMPT_PATH}"
        )

    return PROMPT_PATH.read_text(encoding="utf-8").strip()


# ============================================================
# PREPARE PROMO INPUT
# ============================================================

def compact_source_event(event: dict[str, Any]) -> dict[str, Any]:
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


def prepare_segment(segment: dict[str, Any]) -> dict[str, Any]:
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
        "total_duration": promo.get("actual_duration")
        or promo.get("total_duration"),

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
        + "Return exactly one evaluation for every promo_id.\n\n"
        + payload
    )


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
            raise ValueError("An evaluation item is not an object.")

        promo_id = item.get("promo_id")

        if promo_id not in expected_ids:
            raise ValueError(
                f"Unexpected promo_id returned: {promo_id}"
            )

        if promo_id in validated:
            raise ValueError(
                f"Duplicate evaluation returned for {promo_id}"
            )

        for field in SCORE_FIELDS + ["overall_score"]:
            score = item.get(field)

            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 10
            ):
                raise ValueError(
                    f"Invalid {field} score for {promo_id}"
                )

        if item.get("decision") not in DECISIONS:
            raise ValueError(
                f"Invalid decision for {promo_id}"
            )

        for field in [
            "hook_explanation",
            "coherence_explanation",
            "flow_explanation",
            "cliffhanger_explanation",
            "one_line_pitch",
            "improvement_suggestion",
        ]:
            if not isinstance(item.get(field), str):
                raise ValueError(
                    f"Missing or invalid {field} for {promo_id}"
                )

        for field in ["strengths", "weaknesses"]:
            if not isinstance(item.get(field), list):
                raise ValueError(
                    f"Invalid {field} for {promo_id}"
                )

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
    client: genai.Client,
    batch: list[dict[str, Any]],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, dict[str, Any]]:
    """Evaluate one batch of promos using Gemini."""

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
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                },
            )

            response_text = getattr(
                response,
                "text",
                None,
            )

            if not response_text:
                raise ValueError(
                    "Gemini returned an empty response."
                )

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
) -> dict[str, Any]:
    """
    Evaluate structurally valid promos.

    Invalid promos are retained in the result but are not sent to Gemini.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    resolved_api_key = (
        api_key
        or os.getenv("GEMINI_API_KEY")
    )

    if not resolved_api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is missing. "
            "Check your .env file."
        )

    resolved_model = model or DEFAULT_MODEL

    system_prompt = load_evaluation_prompt()

    valid_promos = validation_results.get(
        "valid_promos",
        [],
    )

    invalid_promos = validation_results.get(
        "invalid_promos",
        [],
    )

    print("\n========== PROMO EVALUATOR ==========")
    print(f"Valid promos received: {len(valid_promos)}")
    print(f"Invalid promos skipped: {len(invalid_promos)}")
    print(f"Batch size: {batch_size}")
    print(f"Gemini model: {resolved_model}")

    client = genai.Client(
        api_key=resolved_api_key
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
# SAVE RESULTS
# ============================================================

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

    with destination.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
        )

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
# STANDALONE EXECUTION
# ============================================================


if __name__ == "__main__":

    # 1. Load the latest structurally validated promos.
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    VALIDATION_INPUT_PATH = (
        PROJECT_ROOT
        / "outputs"
        / "raw"
        / "promo_validation_results.json"
    )

    if not VALIDATION_INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Validation results not found: {VALIDATION_INPUT_PATH}"
        )

    with VALIDATION_INPUT_PATH.open("r", encoding="utf-8") as file:
        validation_results = json.load(file)

    valid_promos = validation_results.get("valid_promos", [])
    invalid_promos = validation_results.get("invalid_promos", [])

    if not isinstance(valid_promos, list):
        raise ValueError("valid_promos must be a list.")

    print("\n========== EVALUATION INPUT ==========")
    print(f"Validated promos loaded: {len(valid_promos)}")
    print(f"Invalid promos: {len(invalid_promos)}")
    print("======================================")

    # 2. Load previous evaluations, if available.
    previous_evaluations = {}

    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open("r", encoding="utf-8") as file:
            previous_results = json.load(file)

        for item in previous_results.get("evaluated_promos", []):
            promo_id = item.get("promo_id")
            evaluation = item.get("evaluation")

            if promo_id and isinstance(evaluation, dict):
                previous_evaluations[promo_id] = item

    # 3. Reuse evaluations only when the promo content is unchanged.
    reused_promos = []
    pending_promos = []

    for promo in valid_promos:
        promo_id = promo.get("promo_id")
        previous_item = previous_evaluations.get(promo_id)

        if previous_item:
            current_payload = prepare_promo_for_evaluation(promo)
            previous_payload = prepare_promo_for_evaluation(previous_item)

            if current_payload == previous_payload:
                reused_item = dict(promo)
                reused_item["evaluation"] = previous_item["evaluation"]
                reused_item["evaluation_status"] = "completed"

                reused_promos.append(reused_item)
                continue

        pending_promos.append(promo)

    print("\n========== INCREMENTAL EVALUATION ==========")
    print(f"Previous evaluations reused: {len(reused_promos)}")
    print(f"Promos requiring new evaluation: {len(pending_promos)}")
    print("============================================")

    # 4. Evaluate only new or changed promos.
    newly_evaluated = []

    if pending_promos:
        new_results = evaluate_promos(
            {
                "valid_promos": pending_promos,
                "invalid_promos": [],
            },
            batch_size=DEFAULT_BATCH_SIZE,
        )

        newly_evaluated = new_results["evaluated_promos"]

    else:
        print("\nAll promos already have matching evaluations.")
        new_results = {"statistics": {"total_batches": 0}}

    # 5. Combine reused and newly evaluated results.
    evaluated_promos = reused_promos + newly_evaluated

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

    # 6. Create the complete evaluation result.
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
            "total_batches": new_results["statistics"]["total_batches"],
            "model": DEFAULT_MODEL,
        },
    }

    # 7. Save and display results.
    save_evaluation_results(results)
    print_evaluation_summary(results)

    print("\n========== FINAL EVALUATION SUMMARY ==========")
    print(f"Validated promos: {len(valid_promos)}")
    print(f"Evaluated promos: {len(evaluated_promos)}")
    print(f"Reused evaluations: {len(reused_promos)}")
    print(f"New evaluations: {len(newly_evaluated)}")
    print(f"Recommended: {len(recommended)}")
    print(f"Needs revision: {len(needs_revision)}")
    print(f"Rejected: {len(rejected)}")
    print("==============================================")

