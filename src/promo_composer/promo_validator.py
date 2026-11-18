
from collections import Counter
from copy import deepcopy
import re


# ============================================================
# CONFIGURATION
# ============================================================

MIN_PROMO_DURATION = 20.0
MAX_PROMO_DURATION = 60.0

HOOK_WINDOW_SECONDS = 3.0
CLIFFHANGER_WINDOW_SECONDS = 3.0

TIMESTAMP_TOLERANCE = 0.15

VALID_CONSTRUCTION_TYPES = {
    "single_continuous_segment",
    "cross_episode_combination",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value, default=None):
    """Convert a value to float safely."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_text(value):
    """Normalize text values."""
    if value is None:
        return ""
    return str(value).strip()


def is_valid_episode(episode):
    """Check whether an episode identifier is valid."""
    if not episode:
        return False

    return bool(
        re.fullmatch(r"EP\d+", str(episode).upper())
    )


def calculate_duration(start_time, end_time):
    """Calculate duration from source timestamps."""
    start = safe_float(start_time)
    end = safe_float(end_time)

    if start is None or end is None:
        return None

    duration = end - start

    if duration <= 0:
        return None

    return round(duration, 3)


def add_error(errors, code, message):
    """Add a hard validation failure."""
    errors.append({
        "code": code,
        "message": message,
    })


def add_warning(warnings, code, message):
    """Add a quality warning."""
    warnings.append({
        "code": code,
        "message": message,
    })


# ============================================================
# 1. VALIDATE PROMO STRUCTURE
# ============================================================

def validate_promo_structure(promo, errors, warnings):
    """Check required promo-level fields."""

    required_fields = [
        "promo_id",
        "construction_type",
        "segments",
        "segment_count",
        "total_duration",
    ]

    for field in required_fields:
        if field not in promo:
            add_error(
                errors,
                "MISSING_PROMO_FIELD",
                f"Required promo field is missing: {field}",
            )

    if not promo.get("promo_id"):
        add_error(
            errors,
            "INVALID_PROMO_ID",
            "Promo ID is empty.",
        )

    construction_type = promo.get("construction_type")

    if construction_type not in VALID_CONSTRUCTION_TYPES:
        add_error(
            errors,
            "INVALID_CONSTRUCTION_TYPE",
            f"Unsupported construction type: {construction_type}",
        )

    segments = promo.get("segments")

    if not isinstance(segments, list) or not segments:
        add_error(
            errors,
            "EMPTY_SEGMENTS",
            "Promo must contain at least one segment.",
        )
        return

    declared_count = promo.get("segment_count")

    if declared_count != len(segments):
        add_error(
            errors,
            "SEGMENT_COUNT_MISMATCH",
            "Declared segment count does not match actual segments.",
        )

    if (
        construction_type == "single_continuous_segment"
        and len(segments) != 1
    ):
        add_error(
            errors,
            "INVALID_SINGLE_SEGMENT_PROMO",
            "A single continuous promo must contain exactly one segment.",
        )

    if (
        construction_type == "cross_episode_combination"
        and len(segments) < 2
    ):
        add_error(
            errors,
            "INVALID_MULTI_SEGMENT_PROMO",
            "A cross-episode promo must contain at least two segments.",
        )


# ============================================================
# 2. VALIDATE INDIVIDUAL SEGMENTS
# ============================================================

def validate_segment(segment, index, errors, warnings):
    """Validate one source segment."""

    prefix = f"Segment {index}"

    required_fields = [
        "segment_order",
        "episode",
        "start_time",
        "end_time",
        "duration",
    ]

    for field in required_fields:
        if field not in segment:
            add_error(
                errors,
                "MISSING_SEGMENT_FIELD",
                f"{prefix}: required field '{field}' is missing.",
            )

    episode = segment.get("episode")

    if not is_valid_episode(episode):
        add_error(
            errors,
            "INVALID_EPISODE",
            f"{prefix}: invalid or missing episode ID.",
        )

    start = safe_float(segment.get("start_time"))
    end = safe_float(segment.get("end_time"))
    declared_duration = safe_float(segment.get("duration"))

    if start is None or end is None:
        add_error(
            errors,
            "INVALID_TIMESTAMP",
            f"{prefix}: start or end timestamp is not numeric.",
        )
        return None

    if start < 0:
        add_error(
            errors,
            "NEGATIVE_TIMESTAMP",
            f"{prefix}: start timestamp cannot be negative.",
        )

    actual_duration = calculate_duration(start, end)

    if actual_duration is None:
        add_error(
            errors,
            "INVALID_SEGMENT_DURATION",
            f"{prefix}: end timestamp must be greater than start timestamp.",
        )
        return None

    if declared_duration is None:
        add_error(
            errors,
            "MISSING_SEGMENT_DURATION",
            f"{prefix}: segment duration is missing or invalid.",
        )

    elif abs(actual_duration - declared_duration) > TIMESTAMP_TOLERANCE:
        add_error(
            errors,
            "SEGMENT_DURATION_MISMATCH",
            f"{prefix}: declared duration does not match source timestamps.",
        )

    if not segment.get("segment_id"):
        add_error(
            errors,
            "MISSING_SEGMENT_ID",
            f"{prefix}: segment ID is missing.",
        )

    if not segment.get("event_ids") and not segment.get("event_id"):
        add_warning(
            warnings,
            "MISSING_SOURCE_EVENT_REFERENCE",
            f"{prefix}: no screenplay event ID is attached.",
        )

    if not segment.get("source_events"):
        if not normalize_text(segment.get("text")):
            add_warning(
                warnings,
                "MISSING_SOURCE_TEXT",
                f"{prefix}: no source screenplay text is available.",
            )

    return {
        "episode": str(episode).upper() if episode else None,
        "start_time": start,
        "end_time": end,
        "duration": actual_duration,
        "segment_order": segment.get("segment_order"),
        "segment_id": segment.get("segment_id"),
    }


# ============================================================
# 3. VALIDATE SEGMENT ORDER
# ============================================================

def validate_segment_order(segments, errors):
    """
    Check that segment_order follows the actual viewing order.

    We deliberately do not require episode chronology:
    editorial promo sequences may reorder scenes.
    """
    orders = []

    for segment in segments:
        order = segment.get("segment_order")

        if isinstance(order, bool) or not isinstance(order, int):
            add_error(
                errors,
                "INVALID_SEGMENT_ORDER",
                "Every segment must have an integer segment_order.",
            )
            continue

        orders.append(order)

    if len(orders) != len(segments):
        return

    expected = list(range(1, len(segments) + 1))

    if orders != expected:
        add_error(
            errors,
            "INCORRECT_SEGMENT_ORDER",
            "Segment orders must be consecutive, starting from 1.",
        )


# ============================================================
# 4. VALIDATE DUPLICATE AND OVERLAPPING FOOTAGE
# ============================================================

def validate_duplicate_segments(normalized_segments, errors):
    """Detect duplicate segment IDs and duplicate source events."""

    segment_ids = [
        item["segment_id"]
        for item in normalized_segments
        if item["segment_id"]
    ]

    duplicates = [
        item
        for item, count in Counter(segment_ids).items()
        if count > 1
    ]

    for duplicate in duplicates:
        add_error(
            errors,
            "DUPLICATE_SEGMENT",
            f"Segment ID appears more than once: {duplicate}",
        )

    
    # Collect unique event references within each segment.
    # The anchor event_id may already exist in event_ids,
    # so it must not be counted twice within the same segment.

    event_references = []

    for segment in normalized_segments:
        episode = segment["episode"]

        segment_event_ids = set(segment.get("event_ids") or [])

        anchor_event_id = segment.get("event_id")
        if anchor_event_id:
            segment_event_ids.add(anchor_event_id)

        for event_id in segment_event_ids:
            if event_id:
                event_references.append((episode, event_id))

    # Detect an event reused across different segments.
    duplicate_events = [
        item
        for item, count in Counter(event_references).items()
        if count > 1
    ]

    for episode, event_id in duplicate_events:
        add_error(
            errors,
            "DUPLICATE_SOURCE_EVENT",
            f"Source event {event_id} from {episode} is used more than once.",
        )



def validate_overlapping_segments(normalized_segments, errors):
    """
    Detect overlapping source timestamps within the same episode.

    Segments from different episodes are allowed to have identical
    timestamps because their source timelines are independent.
    """
    by_episode = {}

    for segment in normalized_segments:
        episode = segment["episode"]

        if not episode:
            continue

        by_episode.setdefault(episode, []).append(segment)

    for episode, segments in by_episode.items():
        ordered = sorted(
            segments,
            key=lambda item: item["start_time"]
        )

        for index in range(len(ordered) - 1):
            current = ordered[index]
            following = ordered[index + 1]

            if following["start_time"] < current["end_time"]:
                add_error(
                    errors,
                    "OVERLAPPING_SOURCE_SEGMENTS",
                    (
                        f"Segments overlap in {episode}: "
                        f"{current['segment_id']} and "
                        f"{following['segment_id']}."
                    ),
                )


# ============================================================
# 5. VALIDATE TOTAL PROMO DURATION
# ============================================================

def validate_promo_duration(
    promo,
    normalized_segments,
    errors,
):
    """Validate total duration against actual segment timestamps."""

    if not normalized_segments:
        return None

    actual_total = round(
        sum(
            item["duration"]
            for item in normalized_segments
        ),
        3,
    )

    declared_total = safe_float(
        promo.get("total_duration")
    )

    if declared_total is None:
        add_error(
            errors,
            "INVALID_TOTAL_DURATION",
            "Promo total duration is missing or invalid.",
        )

    elif abs(actual_total - declared_total) > TIMESTAMP_TOLERANCE:
        add_error(
            errors,
            "TOTAL_DURATION_MISMATCH",
            (
                f"Declared duration {declared_total} does not match "
                f"calculated duration {actual_total}."
            ),
        )

    if actual_total < MIN_PROMO_DURATION:
        add_error(
            errors,
            "PROMO_TOO_SHORT",
            (
                f"Promo duration is {actual_total} seconds; "
                f"minimum is {MIN_PROMO_DURATION} seconds."
            ),
        )

    elif actual_total > MAX_PROMO_DURATION:
        add_error(
            errors,
            "PROMO_TOO_LONG",
            (
                f"Promo duration is {actual_total} seconds; "
                f"maximum is {MAX_PROMO_DURATION} seconds."
            ),
        )

    return actual_total


# ============================================================
# 6. VALIDATE HOOK EVIDENCE
# ============================================================

def validate_hook(promo, normalized_segments, warnings):
    """
    Check whether source evidence exists in the first three seconds.

    This checks evidence location, not whether the evidence is
    actually attention-grabbing.
    """
    hook = promo.get("hook", {})

    if not isinstance(hook, dict):
        add_warning(
            warnings,
            "MISSING_HOOK_METADATA",
            "Hook metadata is missing or invalid.",
        )
        return

    if not normalized_segments:
        return

    first_segment = normalized_segments[0]

    promo_start = first_segment["start_time"]
    hook_window_end = promo_start + HOOK_WINDOW_SECONDS

    evidence_timestamp = safe_float(
        hook.get("timestamp")
    )

    evidence_text = normalize_text(
        hook.get("evidence_text")
    )

    if not hook.get("identified"):
        add_warning(
            warnings,
            "HOOK_NOT_IDENTIFIED",
            "No opening hook evidence was identified.",
        )
        return

    if not evidence_text:
        add_warning(
            warnings,
            "HOOK_EVIDENCE_TEXT_MISSING",
            "Hook is marked identified but has no evidence text.",
        )

    if evidence_timestamp is None:
        add_warning(
            warnings,
            "HOOK_TIMESTAMP_MISSING",
            "Hook evidence has no valid timestamp.",
        )
        return

    if (
        evidence_timestamp < promo_start
        or evidence_timestamp > hook_window_end
    ):
        add_warning(
            warnings,
            "HOOK_OUTSIDE_OPENING_WINDOW",
            (
                "Hook evidence is not located within the first "
                "three seconds of the promo."
            ),
        )


# ============================================================
# 7. VALIDATE CLIFFHANGER EVIDENCE
# ============================================================

def validate_cliffhanger(
    promo,
    normalized_segments,
    warnings,
):
    """
    Check whether source evidence exists in the final three seconds.

    This does not establish that the ending is unresolved.
    """
    cliffhanger = promo.get("cliffhanger", {})

    if not isinstance(cliffhanger, dict):
        add_warning(
            warnings,
            "MISSING_CLIFFHANGER_METADATA",
            "Cliffhanger metadata is missing or invalid.",
        )
        return

    if not normalized_segments:
        return

    last_segment = normalized_segments[-1]

    promo_end = last_segment["end_time"]
    window_start = promo_end - CLIFFHANGER_WINDOW_SECONDS

    evidence_timestamp = safe_float(
        cliffhanger.get("timestamp")
    )

    evidence_text = normalize_text(
        cliffhanger.get("evidence_text")
    )

    if not cliffhanger.get("identified"):
        add_warning(
            warnings,
            "CLIFFHANGER_NOT_IDENTIFIED",
            "No ending evidence was identified.",
        )
        return

    if not evidence_text:
        add_warning(
            warnings,
            "CLIFFHANGER_EVIDENCE_TEXT_MISSING",
            (
                "Ending is marked identified but has no "
                "evidence text."
            ),
        )

    if evidence_timestamp is None:
        add_warning(
            warnings,
            "CLIFFHANGER_TIMESTAMP_MISSING",
            "Ending evidence has no valid timestamp.",
        )
        return

    if (
        evidence_timestamp < window_start
        or evidence_timestamp > promo_end
    ):
        add_warning(
            warnings,
            "CLIFFHANGER_OUTSIDE_ENDING_WINDOW",
            (
                "Ending evidence is not located within the final "
                "three seconds of the promo."
            ),
        )


# ============================================================
# 8. VALIDATE EPISODE METADATA
# ============================================================

def validate_episode_metadata(
    promo,
    normalized_segments,
    errors,
):
    """Check whether promo episode metadata matches its segments."""

    actual_episodes = []

    for segment in normalized_segments:
        episode = segment["episode"]

        if episode and episode not in actual_episodes:
            actual_episodes.append(episode)

    declared_episodes = promo.get("episodes", [])

    if not isinstance(declared_episodes, list):
        add_error(
            errors,
            "INVALID_EPISODE_METADATA",
            "Promo episodes field must be a list.",
        )
        return

    normalized_declared = [
        str(item).upper()
        for item in declared_episodes
        if item
    ]

    if set(normalized_declared) != set(actual_episodes):
        add_error(
            errors,
            "EPISODE_METADATA_MISMATCH",
            "Declared episode list does not match the segment episodes.",
        )


# ============================================================
# 9. MAIN SINGLE-PROMO VALIDATOR
# ============================================================

def validate_promo(promo):
    """
    Validate one complete promo.

    Returns:
        promo:
            Original promo with validation metadata.

        errors:
            Hard validation failures.

        warnings:
            Quality warnings.

        validation_status:
            passed or failed.
    """
    promo = deepcopy(promo)

    errors = []
    warnings = []

    if not isinstance(promo, dict):
        return {
            "promo_id": None,
            "validation_status": "failed",
            "is_valid": False,
            "errors": [{
                "code": "INVALID_PROMO_OBJECT",
                "message": "Promo must be a dictionary.",
            }],
            "warnings": [],
        }

    validate_promo_structure(
        promo,
        errors,
        warnings,
    )

    segments = promo.get("segments", [])

    if not isinstance(segments, list) or not segments:
        segments = []

    normalized_segments = []

    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            add_error(
                errors,
                "INVALID_SEGMENT_OBJECT",
                f"Segment {index} must be a dictionary.",
            )
            continue

        normalized = validate_segment(
            segment,
            index,
            errors,
            warnings,
        )

        if normalized:
            normalized["event_ids"] = segment.get(
                "event_ids", []
            )

            normalized["event_id"] = segment.get(
                "event_id"
            )

            normalized_segments.append(normalized)

    validate_segment_order(
        segments,
        errors,
    )

    validate_duplicate_segments(
        normalized_segments,
        errors,
    )

    validate_overlapping_segments(
        normalized_segments,
        errors,
    )

    actual_total = validate_promo_duration(
        promo,
        normalized_segments,
        errors,
    )

    validate_episode_metadata(
        promo,
        normalized_segments,
        errors,
    )

    validate_hook(
        promo,
        normalized_segments,
        warnings,
    )

    validate_cliffhanger(
        promo,
        normalized_segments,
        warnings,
    )

    # Standalone coherence cannot be established by timestamp
    # checks. It is assessed by the complete-promo evaluator.
    add_warning(
        warnings,
        "STANDALONE_COHERENCE_PENDING",
        (
            "Standalone coherence and audience comprehension "
            "must be assessed by promo_evaluator.py."
        ),
    )

    validation_status = (
        "passed" if not errors else "failed"
    )

    promo["actual_duration"] = actual_total
    promo["validation_status"] = validation_status
    promo["validation_errors"] = errors
    promo["validation_warnings"] = warnings
    promo["is_valid"] = validation_status == "passed"

    return promo


# ============================================================
# 10. VALIDATE ALL PROMOS
# ============================================================

def validate_promos(builder_results):
    """
    Validate every promo returned by build_promos().

    Input:
        builder_results:
            Output returned by build_promos().

    Returns:
        validated_promos:
            All promo candidates with validation metadata.

        valid_promos:
            Candidates passing all hard checks.

        invalid_promos:
            Candidates failing at least one hard check.

        statistics:
            Validation summary.
    """
    promos = builder_results.get("promos", [])

    print("\n========== PROMO VALIDATOR ==========")

    print(f"Promos received: {len(promos)}")

    validated_promos = []

    for promo in promos:
        result = validate_promo(promo)
        validated_promos.append(result)

    valid_promos = [
        promo
        for promo in validated_promos
        if promo["is_valid"]
    ]

    invalid_promos = [
        promo
        for promo in validated_promos
        if not promo["is_valid"]
    ]

    warning_count = sum(
        len(promo.get("validation_warnings", []))
        for promo in validated_promos
    )

    error_count = sum(
        len(promo.get("validation_errors", []))
        for promo in validated_promos
    )

    statistics = {
        "total_promos_received": len(promos),
        "valid_promos": len(valid_promos),
        "invalid_promos": len(invalid_promos),
        "total_hard_errors": error_count,
        "total_quality_warnings": warning_count,
        "promos_with_hook_warnings": sum(
            any(
                warning["code"].startswith("HOOK_")
                for warning in promo["validation_warnings"]
            )
            for promo in validated_promos
        ),
        "promos_with_cliffhanger_warnings": sum(
            any(
                warning["code"].startswith("CLIFFHANGER_")
                for warning in promo["validation_warnings"]
            )
            for promo in validated_promos
        ),
        "duration_min": MIN_PROMO_DURATION,
        "duration_max": MAX_PROMO_DURATION,
    }

    print("\nValidation completed.")

    print(
        f"Valid promos: {statistics['valid_promos']}"
    )

    print(
        f"Invalid promos: {statistics['invalid_promos']}"
    )

    print(
        f"Hard errors: {statistics['total_hard_errors']}"
    )

    print(
        f"Quality warnings: {statistics['total_quality_warnings']}"
    )

    print("====================================\n")

    return {
        "validated_promos": validated_promos,
        "valid_promos": valid_promos,
        "invalid_promos": invalid_promos,
        "statistics": statistics,
    }


# ============================================================
# 11. PRINT VALIDATION SUMMARY
# ============================================================

def print_validation_summary(results, limit=15):
    """Print validation results in a readable format."""

    print("\n========== VALIDATION SUMMARY ==========")

    for promo in results.get("validated_promos", [])[:limit]:
        print(
            f"\n{promo.get('promo_id')} | "
            f"{promo.get('validation_status')}"
        )

        print(
            f"Duration: {promo.get('actual_duration')} seconds"
        )

        print(
            f"Errors: {len(promo.get('validation_errors', []))}"
        )

        print(
            f"Warnings: {len(promo.get('validation_warnings', []))}"
        )

        for error in promo.get("validation_errors", []):
            print(
                f"  ERROR [{error['code']}]: "
                f"{error['message']}"
            )

        for warning in promo.get("validation_warnings", []):
            print(
                f"  WARNING [{warning['code']}]: "
                f"{warning['message']}"
            )

    print("\n========================================")


# ============================================================
# 12. STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":
    from src.promo_composer.candidate_loader import (
        load_promo_composer_data
    )

    from src.promo_composer.segment_selector import (
        select_promo_segments
    )

    from src.promo_composer.promo_builder import (
        build_promos
    )

    # Load project data.
    data = load_promo_composer_data()

    # Run segment selection.
    selection_results = select_promo_segments(data)

    # Construct promo candidates.
    builder_results = build_promos(selection_results)

    # Validate constructed promos.
    validation_results = validate_promos(builder_results)

    # Display results.
    print_validation_summary(validation_results)
