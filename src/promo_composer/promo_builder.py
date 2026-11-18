
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

MIN_PROMO_DURATION = 20.0
MAX_PROMO_DURATION = 60.0

HOOK_WINDOW_SECONDS = 3.0
CLIFFHANGER_WINDOW_SECONDS = 3.0

MAX_PROMOS_FROM_CANDIDATES = 100
MAX_PROMOS_FROM_COMBINATIONS = 40


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
    """Convert text to a clean string."""
    if value is None:
        return ""

    return str(value).strip()


def calculate_segment_duration(segment):
    """Calculate segment duration from source timestamps."""
    start = safe_float(segment.get("start_time"))
    end = safe_float(segment.get("end_time"))

    if start is None or end is None:
        return None

    duration = end - start

    if duration <= 0:
        return None

    return round(duration, 3)


def calculate_total_duration(segments):
    """Calculate total duration of all promo segments."""
    total = 0.0

    for segment in segments:
        duration = calculate_segment_duration(segment)

        if duration is None:
            return None

        total += duration

    return round(total, 3)


def is_valid_promo_duration(duration):
    """Check the Kuku assignment's 20-60 second requirement."""
    return (
        duration is not None
        and MIN_PROMO_DURATION <= duration <= MAX_PROMO_DURATION
    )


# ============================================================
# 1. STANDARDIZE SOURCE SEGMENTS
# ============================================================

def standardize_candidate_segment(segment, order):
    """
    Convert an individual Layer 2 candidate into the
    standard promo segment structure.
    """
    duration = calculate_segment_duration(segment)

    if duration is None:
        return None

    return {
        "segment_order": order,
        "segment_id": segment.get("segment_id"),
        "source_type": segment.get("source_type"),
        "candidate_id": segment.get("candidate_id"),
        "event_id": segment.get("event_id"),
        "episode": segment.get("episode"),
        "scene_number": segment.get("scene_number"),
        "start_time": safe_float(segment.get("start_time")),
        "end_time": safe_float(segment.get("end_time")),
        "duration": duration,
        "event_ids": segment.get("event_ids", []),
        "source_events": segment.get("source_events", []),
        "text": normalize_text(segment.get("text")),
    }


def standardize_combination_segment(segment, order):
    """
    Convert a cross-episode source interval into the
    standard promo segment structure.

    Preserve the original candidate ID, event IDs,
    source events and timestamps.
    """

    duration = calculate_segment_duration(segment)

    if duration is None:
        return None

    event_id = (
        segment.get("anchor_event_id")
        or segment.get("event_id")
    )

    event_ids = segment.get("event_ids", [])

    if not event_ids and event_id:
        event_ids = [event_id]

    source_events = segment.get("source_events", [])

    # Preserve a source event for older event-level segments
    # if the segment does not already contain source events.
    if not source_events and event_id:
        source_events = [{
            "event_id": event_id,
            "text": segment.get("text", ""),
            "start_time": segment.get("start_time"),
            "end_time": segment.get("end_time"),
        }]

    return {
        "segment_order": order,
        "segment_id": segment.get("segment_id"),
        "source_type": segment.get("source_type"),
        "candidate_id": segment.get("candidate_id"),
        "event_id": event_id,
        "episode": segment.get("episode"),
        "scene_number": segment.get("scene_number"),
        "start_time": safe_float(segment.get("start_time")),
        "end_time": safe_float(segment.get("end_time")),
        "duration": duration,
        "event_ids": event_ids,
        "source_events": source_events,
        "text": normalize_text(segment.get("text")),
    }
# ============================================================
# 2. FIND OPENING HOOK EVIDENCE
# ============================================================

def get_source_events(segment):
    """
    Retrieve source screenplay events associated with a segment.
    """
    events = segment.get("source_events", [])

    if events:
        return events

    # Event-level segments already contain their own event text.
    if segment.get("event_id"):
        return [{
            "event_id": segment.get("event_id"),
            "text": segment.get("text"),
            "start_time": segment.get("start_time"),
            "end_time": segment.get("end_time"),
        }]

    return []


def find_boundary_event(
    segments,
    boundary,
    window_seconds=HOOK_WINDOW_SECONDS,
):
    """
    Find screenplay evidence close to the opening or ending
    of a promo.

    boundary:
        "opening" or "ending"

    Only source events whose timestamps overlap the requested
    time window are considered.
    """
    if not segments:
        return None

    if boundary == "opening":
        first_segment = segments[0]

        window_start = first_segment["start_time"]
        window_end = window_start + window_seconds

        search_segments = [first_segment]

    elif boundary == "ending":
        last_segment = segments[-1]

        window_end = last_segment["end_time"]
        window_start = window_end - window_seconds

        search_segments = [last_segment]

    else:
        raise ValueError(
            "boundary must be 'opening' or 'ending'"
        )

    matching_events = []

    for segment in search_segments:
        for event in get_source_events(segment):
            event_start = safe_float(event.get("start_time"))
            event_end = safe_float(event.get("end_time"))

            if event_start is None or event_end is None:
                continue

            # The event must overlap the relevant boundary window.
            overlaps = (
                event_start < window_end
                and event_end > window_start
            )

            if not overlaps:
                continue

            matching_events.append({
                "event_id": event.get("event_id"),
                "episode": segment.get("episode"),
                "text": normalize_text(event.get("text")),
                "start_time": event_start,
                "end_time": event_end,
                "overlap_start": max(event_start, window_start),
                "overlap_end": min(event_end, window_end),
            })

    if not matching_events:
        return None

    if boundary == "opening":
        matching_events.sort(
            key=lambda item: (
                item["overlap_start"],
                item["start_time"],
            )
        )

    else:
        matching_events.sort(
            key=lambda item: (
                item["overlap_end"],
                item["end_time"],
            ),
            reverse=True,
        )

    return matching_events[0]


# ============================================================
# 3. BUILD HOOK AND CLIFFHANGER METADATA
# ============================================================

def build_hook_metadata(segments):
    """Identify source evidence in the first three seconds."""
    event = find_boundary_event(
        segments,
        boundary="opening",
        window_seconds=HOOK_WINDOW_SECONDS,
    )

    if not event:
        return {
            "identified": False,
            "time_window_seconds": HOOK_WINDOW_SECONDS,
            "evidence_event_id": None,
            "episode": None,
            "timestamp": None,
            "evidence_text": "",
            "description": "",
        }

    return {
        "identified": True,
        "time_window_seconds": HOOK_WINDOW_SECONDS,
        "evidence_event_id": event["event_id"],
        "episode": event["episode"],
        "timestamp": event["start_time"],
        "evidence_text": event["text"],
        "description": (
            "Source screenplay event occurring within the "
            "first three seconds. Its effectiveness as a hook "
            "requires validation."
        ),
    }


def build_cliffhanger_metadata(segments):
    """
    Identify source evidence in the final three seconds.

    This function finds the ending event. It does not claim
    that the event is a genuine unresolved cliffhanger.
    """
    event = find_boundary_event(
        segments,
        boundary="ending",
        window_seconds=CLIFFHANGER_WINDOW_SECONDS,
    )

    if not event:
        return {
            "identified": False,
            "time_window_seconds": CLIFFHANGER_WINDOW_SECONDS,
            "evidence_event_id": None,
            "episode": None,
            "timestamp": None,
            "evidence_text": "",
            "description": "",
        }

    return {
        "identified": True,
        "time_window_seconds": CLIFFHANGER_WINDOW_SECONDS,
        "evidence_event_id": event["event_id"],
        "episode": event["episode"],
        "timestamp": event["end_time"],
        "evidence_text": event["text"],
        "description": (
            "Source screenplay event occurring within the "
            "final three seconds. Whether it creates an "
            "unresolved cliffhanger requires evaluation."
        ),
    }


# ============================================================
# 4. BUILD INDIVIDUAL PROMOS
# ============================================================

def build_single_segment_promo(segment):
    """
    Construct one promo from a continuous Layer 2 candidate.

    A single segment is accepted only when its actual duration
    is between 20 and 60 seconds.
    """
    standardized = standardize_candidate_segment(
        segment,
        order=1,
    )

    if not standardized:
        return None

    segments = [standardized]

    total_duration = calculate_total_duration(segments)

    if not is_valid_promo_duration(total_duration):
        return None

    hook = build_hook_metadata(segments)
    cliffhanger = build_cliffhanger_metadata(segments)

    scores = segment.get("scores", {})

    return {
        "promo_id": f"PROMO_{segment.get('candidate_id')}",
        "construction_type": "single_continuous_segment",
        "source_combination_id": None,
        "segments": segments,
        "segment_count": 1,
        "episodes": [segment.get("episode")],
        "total_duration": total_duration,
        "duration_valid": True,
        "hook": hook,
        "cliffhanger": cliffhanger,
        "hook_score": scores.get("opening_hook"),
        "ending_score": scores.get("ending_strength"),
        "source_selection_score": segment.get(
            "selection_score"
        ),
        "source_evaluation": scores,
        "connection_mode": "single_event_window",
        "connection_explanation": (
            "Promo uses one continuous source segment."
        ),
        "sequence_explanation": (
            "The promo preserves the original continuous "
            "screenplay segment."
        ),
        "promo_rationale": "",
        "requires_manual_review": False,
        "validation_status": "pending",
        "evaluation_status": "pending",
    }


# ============================================================
# 5. BUILD MULTI-SEGMENT PROMOS
# ============================================================

def build_multi_segment_promo(combination):
    """
    Construct a promo from a verified cross-episode combination.

    The actual sum of source segment durations must satisfy
    the 20-60 second requirement.
    """
    source_segments = combination.get(
        "ordered_segments", []
    )

    if len(source_segments) < 2:
        return None

    standardized_segments = []

    for order, segment in enumerate(
        source_segments,
        start=1,
    ):
        standardized = standardize_combination_segment(
            segment,
            order=order,
        )

        if not standardized:
            return None

        standardized_segments.append(standardized)

    total_duration = calculate_total_duration(
        standardized_segments
    )

    if not is_valid_promo_duration(total_duration):
        return None

    hook = build_hook_metadata(standardized_segments)
    cliffhanger = build_cliffhanger_metadata(
        standardized_segments
    )

    episodes = []

    for segment in standardized_segments:
        episode = segment.get("episode")

        if episode and episode not in episodes:
            episodes.append(episode)

    combination_id = combination.get("combination_id")

    return {
        "promo_id": f"PROMO_{combination_id}",
        "construction_type": "cross_episode_combination",
        "source_combination_id": combination_id,
        "segments": standardized_segments,
        "segment_count": len(standardized_segments),
        "episodes": episodes,
        "total_duration": total_duration,
        "duration_valid": True,
        "hook": hook,
        "cliffhanger": cliffhanger,
        "hook_score": None,
        "ending_score": None,
        "source_selection_score": None,
        "source_evaluation": {},
        "connection_mode": combination.get(
            "connection_mode"
        ),
        "connection_explanation": combination.get(
            "connection_explanation", ""
        ),
        "sequence_explanation": combination.get(
            "sequence_explanation", ""
        ),
        "promo_rationale": combination.get(
            "promo_rationale", ""
        ),
        "semantic_score": combination.get(
            "semantic_score"
        ),
        "relationship_type": combination.get(
            "relationship_type"
        ),
        "requires_manual_review": combination.get(
            "requires_manual_review", False
        ),
        "validation_status": "pending",
        "evaluation_status": "pending",
    }


# ============================================================
# 6. MAIN PROMO BUILDER
# ============================================================

def build_promos(
    selection_results,
    max_candidate_promos=MAX_PROMOS_FROM_CANDIDATES,
    max_combination_promos=MAX_PROMOS_FROM_COMBINATIONS,
):
    """
    Build complete promo candidates from segment selector output.

    Input:
        selection_results:
            Output returned by select_promo_segments().

    Returns:
        promos:
            All structurally valid 20-60 second promo candidates.

        rejected:
            Source candidates that could not form valid promos.

        statistics:
            Summary of promo construction.
    """
    candidate_segments = selection_results.get(
        "candidate_segments", []
    )

    combinations = selection_results.get(
        "cross_episode_combinations", []
    )

    print("\n========== PROMO BUILDER ==========")

    print(
        f"Individual segments received: "
        f"{len(candidate_segments)}"
    )

    print(
        f"Cross-episode combinations received: "
        f"{len(combinations)}"
    )

    promos = []
    rejected = []

    # --------------------------------------------------------
    # 1. Build continuous promos
    # --------------------------------------------------------

    for segment in candidate_segments[:max_candidate_promos]:
        promo = build_single_segment_promo(segment)

        if promo:
            promos.append(promo)

        else:
            rejected.append({
                "source_id": segment.get("candidate_id"),
                "source_type": "layer2_candidate",
                "reason": (
                    "Invalid timestamps or actual source "
                    "duration outside 20-60 seconds."
                ),
            })

    # --------------------------------------------------------
    # 2. Build cross-episode promos
    # --------------------------------------------------------

    for combination in combinations[:max_combination_promos]:
        promo = build_multi_segment_promo(combination)

        if promo:
            promos.append(promo)

        else:
            duration = calculate_total_duration(
                combination.get("ordered_segments", [])
            )

            rejected.append({
                "source_id": combination.get("combination_id"),
                "source_type": "cross_episode_combination",
                "actual_duration": duration,
                "reason": (
                    "Invalid timestamps, insufficient segments, "
                    "or combined source duration outside "
                    "20-60 seconds. No artificial duration "
                    "extension was applied."
                ),
            })

    # --------------------------------------------------------
    # 3. Assign stable output order
    # --------------------------------------------------------

    for index, promo in enumerate(promos, start=1):
        promo["construction_order"] = index

    # --------------------------------------------------------
    # 4. Statistics
    # --------------------------------------------------------

    single_promos = [
        promo for promo in promos
        if promo["construction_type"]
        == "single_continuous_segment"
    ]

    multi_promos = [
        promo for promo in promos
        if promo["construction_type"]
        == "cross_episode_combination"
    ]

    statistics = {
        "individual_segments_received": len(candidate_segments),
        "cross_episode_combinations_received": len(combinations),
        "single_segment_promos_built": len(single_promos),
        "multi_segment_promos_built": len(multi_promos),
        "total_promos_built": len(promos),
        "rejected_sources": len(rejected),
        "promos_with_hook_evidence": sum(
            promo["hook"]["identified"]
            for promo in promos
        ),
        "promos_with_ending_evidence": sum(
            promo["cliffhanger"]["identified"]
            for promo in promos
        ),
        "duration_min": MIN_PROMO_DURATION,
        "duration_max": MAX_PROMO_DURATION,
    }

    print("\nPromo construction completed.")

    print(
        f"Single-segment promos: "
        f"{statistics['single_segment_promos_built']}"
    )

    print(
        f"Multi-segment promos: "
        f"{statistics['multi_segment_promos_built']}"
    )

    print(
        f"Total promos built: "
        f"{statistics['total_promos_built']}"
    )

    print(
        f"Rejected sources: "
        f"{statistics['rejected_sources']}"
    )

    print("===================================\n")

    return {
        "promos": promos,
        "rejected": rejected,
        "statistics": statistics,
    }


# ============================================================
# 7. PRINT PROMO SUMMARY
# ============================================================

def print_promo_summary(results):
    """Print a readable summary of constructed promos."""
    print("\n========== CONSTRUCTED PROMOS ==========")

    for promo in results.get("promos", []):
        print(
            f"\n{promo['promo_id']} | "
            f"{promo['construction_type']}"
        )

        print(
            f"Duration: {promo['total_duration']} seconds"
        )

        for segment in promo["segments"]:
            print(
                f"  Segment {segment['segment_order']}: "
                f"{segment['episode']} | "
                f"{segment['start_time']} - "
                f"{segment['end_time']} seconds"
            )

        print(
            "Hook evidence:",
            promo["hook"]["evidence_text"] or "Not identified"
        )

        print(
            "Ending evidence:",
            promo["cliffhanger"]["evidence_text"]
            or "Not identified"
        )

    print("\n========================================")


# ============================================================
# 8. STANDALONE EXECUTION
# ============================================================

if __name__ == "__main__":
    from src.promo_composer.candidate_loader import (
        load_promo_composer_data
    )

    from src.promo_composer.segment_selector import (
        select_promo_segments,
    )

    # Load the existing project data.
    data = load_promo_composer_data()

    # Standalone execution builds individual promos only.
    # Cross-episode combinations are supplied during full
    # pipeline integration after semantic verification.
    selection_results = select_promo_segments(data)

    # Build complete promo candidates.
    builder_results = build_promos(selection_results)

    print_promo_summary(builder_results)
