
import re
from collections import Counter
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

MIN_SEGMENT_DURATION = 1.5
MAX_SEGMENT_DURATION = 60.0

MIN_CANDIDATE_SCORE = 6.0
MIN_SEMANTIC_SCORE = 55

MAX_CANDIDATE_SEGMENTS = 100
MAX_CANDIDATES_PER_EPISODE = 3
MAX_CROSS_EPISODE_PAIRS = 40
MAX_PAIRS_PER_EVENT = 3

VALID_CLASSIFICATIONS = {"strong", "possible"}

VALID_CONNECTION_MODES = {
    "narrative_connection",
    "thematic_connection",
    "emotional_visual_juxtaposition",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value, default=0.0):
    """Convert a value to float without raising an exception."""
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def extract_episode_id(value):
    """Extract a standard episode ID such as EP001."""
    match = re.search(r"EP\d+", str(value).upper())

    if not match:
        return None

    return match.group()


def calculate_duration(start_time, end_time):
    """Calculate duration from source timestamps."""
    start = safe_float(start_time, None)
    end = safe_float(end_time, None)

    if start is None or end is None:
        return None

    duration = end - start

    if duration <= 0:
        return None

    return round(duration, 3)


def is_valid_segment_duration(duration):
    """Check whether a segment has usable timestamps."""
    return (
        duration is not None
        and MIN_SEGMENT_DURATION <= duration <= MAX_SEGMENT_DURATION
    )


def normalize_score(value):
    """Clamp an evaluation score to the 0-10 range."""
    return max(0.0, min(10.0, safe_float(value)))


# ============================================================
# 1. CANDIDATE EVALUATION
# ============================================================

def extract_candidate_scores(candidate):
    """Extract Layer 2 scores and the weighted candidate score."""
    evaluation = candidate.get("evaluation", {})
    scores = evaluation.get("scores", {})

    return {
        "weighted_score": normalize_score(
            evaluation.get("weighted_score")
        ),
        "opening_hook": normalize_score(
            scores.get("opening_hook")
        ),
        "emotional_impact": normalize_score(
            scores.get("emotional_impact")
        ),
        "suspense_curiosity": normalize_score(
            scores.get("suspense_curiosity")
        ),
        "narrative_coherence": normalize_score(
            scores.get("narrative_coherence")
        ),
        "promotional_value": normalize_score(
            scores.get("promotional_value")
        ),
        "ending_strength": normalize_score(
            scores.get("ending_strength")
        ),
    }


def calculate_candidate_priority(scores):
    """
    Calculate a deterministic priority score.

    This is a selection score, not a replacement for Layer 2.
    """
    priority = (
        scores["weighted_score"] * 0.40
        + scores["opening_hook"] * 0.20
        + scores["ending_strength"] * 0.20
        + scores["emotional_impact"] * 0.10
        + scores["suspense_curiosity"] * 0.10
    )

    return round(priority * 10, 2)


# ============================================================
# 2. BUILD INDIVIDUAL CANDIDATE SEGMENTS
# ============================================================

def build_candidate_segment(candidate, event_lookup):
    """
    Convert an existing Layer 2 candidate into a standardized
    promotional segment.
    """
    candidate_id = candidate.get("candidate_id")

    if not candidate_id:
        return None

    episode = extract_episode_id(candidate_id)

    if not episode:
        return None

    start_time = candidate.get("start_time")
    end_time = candidate.get("end_time")

    duration = calculate_duration(start_time, end_time)

    if not is_valid_segment_duration(duration):
        return None

    scores = extract_candidate_scores(candidate)

    if scores["weighted_score"] < MIN_CANDIDATE_SCORE:
        return None

    event_ids = candidate.get("event_ids", [])

    matched_events = [
        event_lookup[event_id]
        for event_id in event_ids
        if event_id in event_lookup
    ]

    return {
        "segment_id": f"SEG_{candidate_id}",
        "source_type": "layer2_candidate",
        "candidate_id": candidate_id,
        "episode": episode,
        "scene_number": candidate.get("scene_number"),
        "start_time": safe_float(start_time),
        "end_time": safe_float(end_time),
        "duration": duration,
        "event_ids": event_ids,
        "event_count": len(event_ids),
        "event_categories": candidate.get(
            "event_categories", []
        ),
        "descriptions": candidate.get("descriptions", []),
        "importance": candidate.get("importance", 0),
        "scores": scores,
        "selection_score": calculate_candidate_priority(scores),
        "strengths": candidate.get(
            "evaluation", {}
        ).get("strengths", []),
        "weaknesses": candidate.get(
            "evaluation", {}
        ).get("weaknesses", []),
        "overall_assessment": candidate.get(
            "evaluation", {}
        ).get("overall_assessment", ""),
        "matched_event_count": len(matched_events),
        "source_events": [
            {
                "event_id": event.get("event_id"),
                "text": event.get("text"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
            }
            for event in matched_events
        ],
    }


def select_candidate_segments(
    evaluated_candidates,
    event_lookup,
    min_candidate_score=MIN_CANDIDATE_SCORE,
    max_segments=MAX_CANDIDATE_SEGMENTS,
    max_per_episode=MAX_CANDIDATES_PER_EPISODE,
):
    """
    Select high-quality individual promotional segments.

    Uses existing Layer 2 evaluations and applies episode diversity.
    """
    selected = []

    for candidate in evaluated_candidates:
        segment = build_candidate_segment(
            candidate,
            event_lookup
        )

        if not segment:
            continue

        if (
            segment["scores"]["weighted_score"]
            < min_candidate_score
        ):
            continue

        selected.append(segment)

    selected.sort(
        key=lambda item: (
            item["selection_score"],
            item["scores"]["weighted_score"],
            item["scores"]["opening_hook"],
            item["scores"]["ending_strength"],
        ),
        reverse=True,
    )

    # Prevent one episode from dominating the selection.
    episode_counts = Counter()
    final_segments = []

    for segment in selected:
        episode = segment["episode"]

        if episode_counts[episode] >= max_per_episode:
            continue

        final_segments.append(segment)
        episode_counts[episode] += 1

        if len(final_segments) >= max_segments:
            break

    return final_segments


# ============================================================
# 3. BUILD EVENT-LEVEL SEGMENTS
# ============================================================

def build_event_segment(event):
    """
    Convert one screenplay event into a timestamped segment.

    These segments are used for cross-episode combinations.
    """
    start_time = event.get("start_time")
    end_time = event.get("end_time")

    duration = calculate_duration(start_time, end_time)

    if not is_valid_segment_duration(duration):
        return None

    event_id = event.get("event_id")

    if not event_id:
        return None

    return {
        "segment_id": f"SEG_{event_id}",
        "source_type": "screenplay_event",
        "event_id": event_id,
        "episode": event.get("episode"),
        "scene_number": event.get("scene_number"),
        "event_type": event.get("type"),
        "speaker": event.get("speaker"),
        "tone": event.get("tone"),
        "start_time": safe_float(start_time),
        "end_time": safe_float(end_time),
        "duration": duration,
        "text": str(event.get("text") or ""),
        "layer1_selected": event.get(
            "layer1_selected", False
        ),
        "importance": event.get("importance", 0),
    }

def build_pair_source_segment(
    anchor_event,
    evaluated_candidates,
    event_lookup,
    screenplay_events,
):
    """
    Build a source interval around a verified anchor event.

    Priority:
    1. Use an existing Layer 2 candidate containing the anchor.
    2. Otherwise, use the exact boundaries of the anchor's
       screenplay scene, provided the scene is 1.5-60 seconds.

    No timestamps are artificially extended.
    """

    anchor_event_id = anchor_event.get("event_id")

    if not anchor_event_id:
        return None

    anchor_start = safe_float(
        anchor_event.get("start_time"), None
    )
    anchor_end = safe_float(
        anchor_event.get("end_time"), None
    )

    if anchor_start is None or anchor_end is None:
        return None

    # --------------------------------------------------------
    # 1. Prefer an existing Layer 2 candidate
    # --------------------------------------------------------

    matching_candidates = []

    for candidate in evaluated_candidates:

        candidate_event_ids = candidate.get("event_ids", [])

        if anchor_event_id not in candidate_event_ids:
            continue

        candidate_start = safe_float(
            candidate.get("start_time"), None
        )
        candidate_end = safe_float(
            candidate.get("end_time"), None
        )

        if candidate_start is None or candidate_end is None:
            continue

        # The candidate must actually contain the anchor event.
        if (
            candidate_start > anchor_start
            or candidate_end < anchor_end
        ):
            continue

        segment = build_candidate_segment(
            candidate,
            event_lookup,
        )

        if not segment:
            continue

        matching_candidates.append(segment)

    if matching_candidates:
        matching_candidates.sort(
            key=lambda item: (
                item["scores"]["weighted_score"],
                item["selection_score"],
            ),
            reverse=True,
        )

        selected = matching_candidates[0].copy()

        selected["anchor_event_id"] = anchor_event_id
        selected["event_id"] = anchor_event_id
        selected["source_type"] = "layer2_candidate"

        return selected

    # --------------------------------------------------------
    # 2. Fallback: exact screenplay scene interval
    # --------------------------------------------------------

    episode = anchor_event.get("episode")
    scene_number = anchor_event.get("scene_number")

    if not episode or scene_number is None:
        return None

    scene_events = [
        event
        for event in screenplay_events
        if (
            event.get("episode") == episode
            and event.get("scene_number") == scene_number
        )
    ]

    if not scene_events:
        return None

    scene_events.sort(
        key=lambda event: (
            safe_float(event.get("start_time"), 0.0),
            safe_float(event.get("end_time"), 0.0),
        )
    )

    scene_start = min(
        safe_float(event.get("start_time"), 0.0)
        for event in scene_events
    )

    scene_end = max(
        safe_float(event.get("end_time"), 0.0)
        for event in scene_events
    )

    duration = calculate_duration(
        scene_start,
        scene_end,
    )

    if not is_valid_segment_duration(duration):
        return None

    if duration > MAX_SEGMENT_DURATION:
        return None

    return {
        "segment_id": f"SEG_SCENE_{episode}_{scene_number}",
        "source_type": "screenplay_scene_window",
        "candidate_id": None,
        "event_id": anchor_event_id,
        "anchor_event_id": anchor_event_id,
        "episode": episode,
        "scene_number": scene_number,
        "start_time": scene_start,
        "end_time": scene_end,
        "duration": duration,
        "event_ids": [
            event.get("event_id")
            for event in scene_events
            if event.get("event_id")
        ],
        "source_events": [
            {
                "event_id": event.get("event_id"),
                "text": event.get("text"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
            }
            for event in scene_events
        ],
        "text": " ".join(
            str(event.get("text") or "").strip()
            for event in scene_events
            if event.get("text")
        ),
        "scores": {},
        "selection_score": None,
    }
# ============================================================
# 4. SEMANTIC PAIR FILTERING
# ============================================================

def get_semantic_score(pair):
    """Read the Semantic Verifier score."""
    verification = pair.get("semantic_verification", {})

    return safe_float(
        verification.get("semantic_score")
    )


def is_eligible_semantic_pair(pair):
    """
    Determine whether a verified pair is suitable for
    further promotional construction.
    """
    verification = pair.get("semantic_verification", {})

    classification = verification.get("classification")
    connection_mode = verification.get("connection_mode")
    best_sequence = verification.get("best_sequence")

    if classification not in VALID_CLASSIFICATIONS:
        return False

    if connection_mode not in VALID_CONNECTION_MODES:
        return False

    if best_sequence == "NEITHER":
        return False

    if get_semantic_score(pair) < MIN_SEMANTIC_SCORE:
        return False

    if verification.get("requires_manual_review", False):
        return False

    event_a = pair.get("event_a", {})
    event_b = pair.get("event_b", {})

    episode_a = event_a.get("episode")
    episode_b = event_b.get("episode")

    if not episode_a or not episode_b:
        return False

    if episode_a == episode_b:
        return False

    return True


# ============================================================
# 5. BUILD CROSS-EPISODE COMBINATIONS
# ============================================================

def build_cross_episode_combination(
    pair,
    evaluated_candidates,
    event_lookup,
    screenplay_events,
):
    """
    Convert a verified semantic pair into an ordered
    two-segment combination using real source intervals.
    """

    verification = pair.get("semantic_verification", {})

    event_a = pair.get("event_a", {})
    event_b = pair.get("event_b", {})

    segment_a = build_pair_source_segment(
        anchor_event=event_a,
        evaluated_candidates=evaluated_candidates,
        event_lookup=event_lookup,
        screenplay_events=screenplay_events,
    )

    segment_b = build_pair_source_segment(
        anchor_event=event_b,
        evaluated_candidates=evaluated_candidates,
        event_lookup=event_lookup,
        screenplay_events=screenplay_events,
    )

    if not segment_a or not segment_b:
        return None

    sequence = verification.get("best_sequence")

    if sequence == "A_THEN_B":
        ordered_segments = [segment_a, segment_b]

    elif sequence == "B_THEN_A":
        ordered_segments = [segment_b, segment_a]

    else:
        ordered_segments = [segment_a, segment_b]

    total_source_duration = round(
        sum(
            segment["duration"]
            for segment in ordered_segments
        ),
        3,
    )

    return {
        "combination_id": verification.get("pair_id"),
        "source_type": "cross_episode_pair",
        "classification": verification.get("classification"),
        "semantic_score": verification.get("semantic_score"),
        "relationship_type": verification.get("relationship_type"),
        "connection_mode": verification.get("connection_mode"),
        "best_sequence": sequence,
        "sequence_is_chronology": False,
        "ordered_segments": ordered_segments,
        "segment_count": len(ordered_segments),
        "combined_source_duration": total_source_duration,
        "connection_explanation": verification.get(
            "connection_explanation", ""
        ),
        "sequence_explanation": verification.get(
            "sequence_explanation", ""
        ),
        "promo_rationale": verification.get(
            "promo_rationale", ""
        ),
        "context_dependency": verification.get(
            "context_dependency"
        ),
        "requires_manual_review": False,
    }
# ============================================================
# 6. SELECT CROSS-EPISODE COMBINATIONS
# ============================================================

def select_cross_episode_combinations(
    verified_pairs,
    evaluated_candidates,
    event_lookup,
    screenplay_events,
    min_semantic_score=MIN_SEMANTIC_SCORE,
    max_pairs=MAX_CROSS_EPISODE_PAIRS,
    max_per_event=MAX_PAIRS_PER_EVENT,
):
    """
    Select verified cross-episode combinations using
    Layer 2 candidate windows or exact screenplay scenes.
    """

    eligible_pairs = []

    for pair in verified_pairs:

        if not is_eligible_semantic_pair(pair):
            continue

        if get_semantic_score(pair) < min_semantic_score:
            continue

        combination = build_cross_episode_combination(
            pair=pair,
            evaluated_candidates=evaluated_candidates,
            event_lookup=event_lookup,
            screenplay_events=screenplay_events,
        )

        if not combination:
            continue

        # Keep only combinations whose real source duration
        # is within the final promo duration requirement.
        if not (
            20.0
            <= combination["combined_source_duration"]
            <= 60.0
        ):
            continue

        eligible_pairs.append(combination)

    eligible_pairs.sort(
        key=lambda item: (
            item["semantic_score"],
            item["classification"] == "strong",
            item["connection_mode"] == "narrative_connection",
        ),
        reverse=True,
    )

    event_counts = Counter()
    selected = []

    for combination in eligible_pairs:

        event_ids = [
            segment.get("anchor_event_id")
            or segment.get("event_id")
            for segment in combination["ordered_segments"]
        ]

        if any(
            event_counts[event_id] >= max_per_event
            for event_id in event_ids
            if event_id
        ):
            continue

        selected.append(combination)

        for event_id in event_ids:
            if event_id:
                event_counts[event_id] += 1

        if len(selected) >= max_pairs:
            break

    return selected
# ============================================================
# 7. MANUAL REVIEW QUEUE
# ============================================================

def collect_manual_review_pairs(verified_pairs):
    """
    Keep uncertain semantic pairs visible for human inspection.

    These pairs are not automatically selected for promo building.
    """
    review_pairs = []

    for pair in verified_pairs:
        verification = pair.get("semantic_verification", {})

        if not verification.get("requires_manual_review", False):
            continue

        review_pairs.append({
            "pair_id": verification.get("pair_id"),
            "event_a_id": pair.get(
                "event_a", {}
            ).get("event_id"),
            "event_b_id": pair.get(
                "event_b", {}
            ).get("event_id"),
            "classification": verification.get("classification"),
            "semantic_score": verification.get("semantic_score"),
            "review_reason": verification.get(
                "manual_review_reason", ""
            ),
        })

    return review_pairs


# ============================================================
# 8. MAIN SEGMENT SELECTION PIPELINE
# ============================================================

def select_promo_segments(
    data,
    verified_pairs=None,
    min_candidate_score=MIN_CANDIDATE_SCORE,
    min_semantic_score=MIN_SEMANTIC_SCORE,
    max_candidate_segments=MAX_CANDIDATE_SEGMENTS,
    max_cross_episode_pairs=MAX_CROSS_EPISODE_PAIRS,
):
    """
    Run the segment selection stage.

    Inputs:
        data:
            Output from load_promo_composer_data().

        verified_pairs:
            Output from verify_candidate_pairs().

    Returns:
        candidate_segments:
            Strong individual Layer 2 candidate windows.

        cross_episode_combinations:
            Semantically verified cross-episode pairs.

        manual_review_pairs:
            Pairs that require human review.

        statistics:
            Selection summary.
    """
    verified_pairs = verified_pairs or []

    screenplay_events = data.get("screenplay_events", [])
    evaluated_candidates = data.get(
        "evaluated_candidates", []
    )

    event_lookup = {
        event["event_id"]: event
        for event in screenplay_events
        if event.get("event_id")
    }

    print("\n========== SEGMENT SELECTION ==========")

    print(
        f"Screenplay events available: "
        f"{len(screenplay_events)}"
    )

    print(
        f"Layer 2 candidates available: "
        f"{len(evaluated_candidates)}"
    )

    print(
        f"Verified semantic pairs available: "
        f"{len(verified_pairs)}"
    )

    # --------------------------------------------------------
    # Individual candidate segments
    # --------------------------------------------------------

    candidate_segments = select_candidate_segments(
        evaluated_candidates=evaluated_candidates,
        event_lookup=event_lookup,
        min_candidate_score=min_candidate_score,
        max_segments=max_candidate_segments,
    )

    # --------------------------------------------------------
    # Cross-episode combinations
    # --------------------------------------------------------

    cross_episode_combinations = select_cross_episode_combinations(
        verified_pairs=verified_pairs,
        evaluated_candidates=evaluated_candidates,
        event_lookup=event_lookup,
        screenplay_events=screenplay_events,
        min_semantic_score=min_semantic_score,
        max_pairs=max_cross_episode_pairs,
    )

    # --------------------------------------------------------
    # Manual review
    # --------------------------------------------------------

    manual_review_pairs = collect_manual_review_pairs(
        verified_pairs
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    statistics = {
        "total_screenplay_events": len(screenplay_events),
        "total_evaluated_candidates": len(evaluated_candidates),
        "total_verified_pairs": len(verified_pairs),
        "selected_candidate_segments": len(candidate_segments),
        "selected_cross_episode_combinations": len(
            cross_episode_combinations
        ),
        "manual_review_pairs": len(manual_review_pairs),
        "candidate_episodes_represented": len({
            item["episode"]
            for item in candidate_segments
        }),
        "cross_episode_pairs_represented": len({
            segment["episode"]
            for combination in cross_episode_combinations
            for segment in combination["ordered_segments"]
        }),
    }

    print("\nSelection completed.")
    print(
        f"Individual segments selected: "
        f"{statistics['selected_candidate_segments']}"
    )
    print(
        f"Cross-episode combinations selected: "
        f"{statistics['selected_cross_episode_combinations']}"
    )
    print(
        f"Pairs requiring manual review: "
        f"{statistics['manual_review_pairs']}"
    )

    print("=======================================\n")

    return {
        "candidate_segments": candidate_segments,
        "cross_episode_combinations": cross_episode_combinations,
        "manual_review_pairs": manual_review_pairs,
        "statistics": statistics,
    }


# ============================================================
# 9. OPTIONAL SUMMARY
# ============================================================

def print_selection_summary(results):
    """Print a compact view of selected segments and combinations."""
    print("\n========== SELECTED CANDIDATE SEGMENTS ==========")

    for index, segment in enumerate(
        results["candidate_segments"][:10],
        start=1,
    ):
        print(
            f"{index}. {segment['candidate_id']} | "
            f"{segment['episode']} | "
            f"{segment['start_time']} - "
            f"{segment['end_time']} sec | "
            f"Score: {segment['scores']['weighted_score']}"
        )

    print("\n========== CROSS-EPISODE COMBINATIONS ==========")

    for index, combination in enumerate(
        results["cross_episode_combinations"][:10],
        start=1,
    ):
        segments = combination["ordered_segments"]

        print(
            f"{index}. {combination['combination_id']} | "
            f"{combination['classification']} | "
            f"Semantic score: {combination['semantic_score']}"
        )

        for segment in segments:
            print(
                f"   {segment['episode']} | "
                f"{segment['event_id']} | "
                f"{segment['start_time']} - "
                f"{segment['end_time']} sec"
            )

    print("=================================================")


if __name__ == "__main__":
    from src.promo_composer.candidate_loader import (
        load_promo_composer_data
    )

    data = load_promo_composer_data()

    # This standalone test selects Layer 2 candidates only.
    # Cross-episode combinations require verified_pairs
    # from semantic_verifier.py.
    results = select_promo_segments(data)

    print_selection_summary(results)