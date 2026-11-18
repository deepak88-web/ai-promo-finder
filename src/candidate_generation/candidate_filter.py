
import math


def validate_candidate(candidate, scene_lookup, min_duration=20, max_duration=60):
    """Validate one candidate clip window."""

    required_fields = [
        "candidate_id",
        "scene_number",
        "start_time",
        "end_time",
        "duration",
        "selection_ids",
        "event_ids"
    ]

    for field in required_fields:
        if field not in candidate:
            return False, f"Missing field: {field}"

    scene = scene_lookup.get(candidate["scene_number"])

    if scene is None:
        return False, "Scene does not exist."

    start = candidate["start_time"]
    end = candidate["end_time"]
    duration = candidate["duration"]

    if not all(
        isinstance(value, (int, float)) and math.isfinite(value)
        for value in (start, end, duration)
    ):
        return False, "Invalid timestamp or duration value."

    scene_start = scene.get("scene_start")
    scene_end = scene.get("scene_end")
    if scene_start is None and scene.get("events"):
        scene_start = min(e["start_time"] for e in scene["events"])
    if scene_end is None and scene.get("events"):
        scene_end = max(e["end_time"] for e in scene["events"])

    if scene_start is not None and start < scene_start - 0.05:
        return False, "Candidate exceeds scene boundaries."
    if scene_end is not None and end > scene_end + 0.05:
        return False, "Candidate exceeds scene boundaries."

    if end <= start:
        return False, "End time must be greater than start time."

    calculated_duration = round(end - start, 2)

    if abs(calculated_duration - duration) > 0.01:
        return False, "Stored duration does not match timestamps."

    if duration < min_duration or duration > max_duration:
        return False, "Duration is outside the allowed range."

    if not candidate["event_ids"]:
        return False, "Candidate has no source events."

    if not candidate["selection_ids"]:
        return False, "Candidate has no dramatic selections."

    return True, "Valid candidate."


def filter_candidates(
    candidates,
    episode,
    min_duration=20,
    max_duration=60
):
    """
    Validate candidate windows and remove invalid or duplicate clips.
    """

    scene_lookup = {
        scene["scene_number"]: scene
        for scene in episode["scenes"]
    }

    valid_candidates = []
    rejected_candidates = []
    seen_signatures = set()

    for candidate in candidates:

        is_valid, reason = validate_candidate(
            candidate,
            scene_lookup,
            min_duration,
            max_duration
        )

        if not is_valid:
            rejected_candidates.append({
                "candidate_id": candidate.get("candidate_id"),
                "reason": reason
            })
            continue

        # Avoid duplicate clips with identical source selections and times.
        signature = (
            candidate["scene_number"],
            candidate["start_time"],
            candidate["end_time"],
            tuple(sorted(set(candidate["event_ids"])))
        )

        if signature in seen_signatures:
            rejected_candidates.append({
                "candidate_id": candidate["candidate_id"],
                "reason": "Duplicate candidate."
            })
            continue

        seen_signatures.add(signature)
        valid_candidates.append(candidate)

    return {
        "valid_candidates": valid_candidates,
        "rejected_candidates": rejected_candidates,
        "total_received": len(candidates),
        "total_valid": len(valid_candidates),
        "total_rejected": len(rejected_candidates)
    }
