
def expand_to_minimum_duration(
    start_time,
    end_time,
    scene_start,
    scene_end,
    min_duration=20
):
    """Expand a dramatic event interval to the minimum clip duration."""

    current_duration = end_time - start_time

    if current_duration >= min_duration:
        return start_time, end_time

    extra_time = min_duration - current_duration

    start_time -= extra_time / 2
    end_time += extra_time / 2

    if start_time < scene_start:
        end_time += scene_start - start_time
        start_time = scene_start

    if end_time > scene_end:
        start_time -= end_time - scene_end
        end_time = scene_end

    start_time = max(start_time, scene_start)

    return round(start_time, 2), round(end_time, 2)


def create_selection_windows(
    analyzed_data,
    episode,
    min_duration=20,
    max_duration=60
):
    """Create timestamp windows for each dramatic selection."""

    scene_lookup = {
        scene["scene_number"]: scene
        for scene in episode["scenes"]
    }

    windows = []

    for selection in analyzed_data["selections"]:

        events_by_scene = {}

        for event in selection["events"]:
            scene_number = event["scene_number"]

            events_by_scene.setdefault(
                scene_number, []
            ).append(event)

        for scene_number, events in events_by_scene.items():

            scene = scene_lookup.get(scene_number)

            if scene is None:
                raise ValueError(
                    f"Scene {scene_number} not found."
                )

            # Sort events chronologically before collecting IDs.
            events = sorted(
                events,
                key=lambda event: (
                    event["start_time"],
                    event["end_time"],
                    event["event_id"]
                )
            )

            start_time = min(
                event["start_time"] for event in events
            )

            end_time = max(
                event["end_time"] for event in events
            )

            start_time, end_time = expand_to_minimum_duration(
                start_time,
                end_time,
                scene["scene_start"],
                scene["scene_end"],
                min_duration
            )

            duration = round(end_time - start_time, 2)

            if duration < min_duration or duration > max_duration:
                continue

            windows.append({
                "scene_number": scene_number,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "selection_ids": [selection["selection_id"]],
                "event_ids": [
                    event["event_id"] for event in events
                ],
                "event_categories": [
                    selection["event_category"]
                ],
                "descriptions": [
                    selection["description"]
                ],
                "importance": selection["importance"]
            })

    return sorted(
        windows,
        key=lambda window: (
            window["scene_number"],
            window["start_time"]
        )
    )


def merge_overlapping_windows(
    windows,
    max_duration=60,
    merge_gap=3
):
    """Merge overlapping or closely spaced windows."""

    if not windows:
        return []

    sorted_windows = sorted(
        windows,
        key=lambda window: (
            window["scene_number"],
            window["start_time"]
        )
    )

    merged = []

    for window in sorted_windows:

        if not merged:
            merged.append(window.copy())
            continue

        previous = merged[-1]

        gap = window["start_time"] - previous["end_time"]

        combined_end = max(
            previous["end_time"],
            window["end_time"]
        )

        combined_duration = (
            combined_end - previous["start_time"]
        )

        can_merge = (
            window["scene_number"] == previous["scene_number"]
            and gap <= merge_gap
            and combined_duration <= max_duration
        )

        if can_merge:
            previous["end_time"] = round(combined_end, 2)
            previous["duration"] = round(
                previous["end_time"] - previous["start_time"], 2
            )

            previous["selection_ids"].extend(
                window["selection_ids"]
            )

            previous["event_ids"].extend(
                window["event_ids"]
            )

            previous["event_categories"].extend(
                window["event_categories"]
            )

            previous["descriptions"].extend(
                window["descriptions"]
            )

            previous["importance"] = max(
                previous["importance"],
                window["importance"]
            )

            # Remove duplicate IDs and restore chronological order.
            previous["event_ids"] = sorted(
                set(previous["event_ids"])
            )

            previous["selection_ids"] = list(
                dict.fromkeys(previous["selection_ids"])
            )

            previous["event_categories"] = list(
                dict.fromkeys(previous["event_categories"])
            )

            previous["descriptions"] = list(
                dict.fromkeys(previous["descriptions"])
            )

        else:
            merged.append(window.copy())

    return merged


def generate_candidate_windows(
    analyzed_data,
    episode,
    min_duration=20,
    max_duration=60,
    merge_gap=3
):
    """Generate and merge valid candidate clip windows."""

    individual_windows = create_selection_windows(
        analyzed_data,
        episode,
        min_duration,
        max_duration
    )

    merged_windows = merge_overlapping_windows(
        individual_windows,
        max_duration,
        merge_gap
    )

    episode_id = analyzed_data["episode"]

    for index, window in enumerate(merged_windows, start=1):
        window["candidate_id"] = (
            f"{episode_id}_C{index:03d}"
        )

    return merged_windows
