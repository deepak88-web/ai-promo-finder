
import re


def get_episode_id(episode_name):
    """Convert 'Episode 22' into 'EP022'."""
    match = re.search(r"\d+", str(episode_name))

    if not match:
        raise ValueError(f"Invalid episode name: {episode_name}")

    return f"EP{int(match.group()):03d}"


def build_event_lookup(episode):
    """
    Build a dictionary mapping generated event IDs
    to their original parsed screenplay event records.
    """
    episode_id = get_episode_id(episode["episode"])
    event_lookup = {}

    for scene in episode["scenes"]:
        scene_number = scene["scene_number"]

        for event_index, event in enumerate(scene["events"], start=1):
            event_id = (
                f"{episode_id}_S{scene_number:03d}"
                f"_E{event_index:03d}"
            )

            event_lookup[event_id] = {
                "event_id": event_id,
                **event
            }

    return event_lookup


def analyze_selections(layer1_result, episode):
    """
    Match Layer 1 event IDs with original screenplay events.
    """

    expected_episode_id = get_episode_id(episode["episode"])

    if layer1_result.get("episode") != expected_episode_id:
        raise ValueError(
            "Layer 1 episode ID does not match parsed episode."
        )

    event_lookup = build_event_lookup(episode)
    analyzed_selections = []

    for selection in layer1_result.get("dramatic_events", []):
        selected_event_ids = selection.get("event_ids", [])

        if not selected_event_ids:
            raise ValueError(
                f"{selection.get('selection_id')} has no event IDs."
            )

        matched_events = []

        for event_id in selected_event_ids:
            if event_id not in event_lookup:
                raise ValueError(
                    f"Event ID not found in screenplay: {event_id}"
                )

            matched_events.append(event_lookup[event_id])

        # Keep events in chronological order.
        matched_events.sort(
            key=lambda event: (
                event["start_time"],
                event["end_time"]
            )
        )

        analyzed_selections.append({
            "selection_id": selection["selection_id"],
            "event_category": selection["event_category"],
            "importance": selection["importance"],
            "description": selection["description"],
            "promotional_reason": selection["promotional_reason"],
            "hook_potential": selection["hook_potential"],
            "ending_potential": selection["ending_potential"],
            "requires_context": selection["requires_context"],
            "events": matched_events
        })

    return {
        "episode": expected_episode_id,
        "selections": analyzed_selections
    }
