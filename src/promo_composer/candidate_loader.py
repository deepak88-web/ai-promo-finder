
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "outputs" / "raw"
PARSED_DATA_PATH = PROJECT_ROOT / "data" / "interim" / "parsed_episodes.json"

TOTAL_EPISODES = 50


def load_json(file_path):
    """Load a JSON file and return its contents."""
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_episode_id(episode_name):
    """Convert an episode name into the standard EP001 format."""
    import re

    match = re.search(r"\d+", str(episode_name))

    if not match:
        raise ValueError(f"Invalid episode name: {episode_name}")

    return f"EP{int(match.group()):03d}"


def build_screenplay_event_pool(parsed_data):
    """
    Collect every screenplay event from all episodes.

    This includes events that were never selected by Layer 1
    or included in the existing candidate windows.
    """
    event_pool = []

    for episode in parsed_data.get("episodes", []):
        episode_id = get_episode_id(episode["episode"])

        for scene in episode.get("scenes", []):
            scene_number = scene["scene_number"]

            for event_index, event in enumerate(
                scene.get("events", []), start=1
            ):
                event_id = (
                    f"{episode_id}_S{scene_number:03d}_E{event_index:03d}"
                )

                event_pool.append({
                    "event_id": event_id,
                    "episode": episode_id,
                    "scene_number": scene_number,
                    "type": event.get("type"),
                    "speaker": event.get("speaker"),
                    "tone": event.get("tone"),
                    "delivery": event.get("delivery"),
                    "start_time": event.get("start_time"),
                    "end_time": event.get("end_time"),
                    "start_timestamp": event.get("start_timestamp"),
                    "end_timestamp": event.get("end_timestamp"),
                    "text": event.get("text"),
                    "layer1_selected": False,
                    "source": "screenplay"
                })

    return event_pool


def load_layer1_events(episode_number, event_lookup, raw_dir=None):
    """Load Layer 1 selections and attach their original screenplay events."""
    base_dir = Path(raw_dir) if raw_dir else RAW_DIR
    file_path = base_dir / f"layer1_episode{episode_number}_events.json"
    if not file_path.exists():
        return []
    layer1_data = load_json(file_path)

    episode_id = f"EP{episode_number:03d}"
    selections = []

    for selection in layer1_data.get("dramatic_events", []):
        event_ids = selection.get("event_ids", [])

        matched_events = []

        for event_id in event_ids:
            if event_id not in event_lookup:
                continue

            matched_events.append(event_lookup[event_id])

        selections.append({
            "selection_id": selection.get("selection_id"),
            "episode": episode_id,
            "event_category": selection.get(
                "event_category",
                selection.get("category")
            ),
            "importance": selection.get("importance"),
            "description": selection.get("description"),
            "promotional_reason": selection.get("promotional_reason"),
            "hook_potential": selection.get("hook_potential"),
            "ending_potential": selection.get("ending_potential"),
            "requires_context": selection.get("requires_context"),
            "event_ids": event_ids,
            "events": matched_events
        })

        for event in matched_events:
            event["layer1_selected"] = True

    return selections


def load_evaluated_candidates(episode_number, raw_dir=None):
    """Load candidate windows and their corresponding Layer 2 evaluations."""
    base_dir = Path(raw_dir) if raw_dir else RAW_DIR
    candidate_path = base_dir / f"candidates_episode{episode_number}.json"
    evaluation_path = (
        base_dir / f"layer2_episode{episode_number}_evaluation.json"
    )

    if not candidate_path.exists() or not evaluation_path.exists():
        return []

    candidate_data = load_json(candidate_path)
    evaluation_data = load_json(evaluation_path)

    evaluations = {
        item["candidate_id"]: item
        for item in evaluation_data.get("evaluated_candidates", [])
    }

    candidates = []

    for candidate in candidate_data.get("candidates", []):
        candidate_id = candidate["candidate_id"]

        if candidate_id not in evaluations:
            continue

        candidates.append({
            **candidate,
            "evaluation": evaluations[candidate_id]
        })

    return candidates


def load_promo_composer_data(
    raw_dir=None,
    parsed_data_path=None,
    episode_numbers=None,
):
    """
    Load all inputs required by the Promo Composer dynamically.

    Returns:
        - evaluated_candidates: Evaluated candidate windows
        - layer1_selections: Dramatic events identified by Layer 1
        - screenplay_events: Every original screenplay event
    """
    import re

    r_dir = Path(raw_dir) if raw_dir else RAW_DIR
    p_path = Path(parsed_data_path) if parsed_data_path else PARSED_DATA_PATH

    if not p_path.exists():
        print(f"Parsed data not found at {p_path}")
        return {
            "episodes_processed": 0,
            "evaluated_candidates": [],
            "layer1_selections": [],
            "screenplay_events": [],
        }

    parsed_data = load_json(p_path)
    screenplay_events = build_screenplay_event_pool(parsed_data)

    event_lookup = {
        event["event_id"]: event
        for event in screenplay_events
    }

    # Discover available episodes
    if episode_numbers is None:
        discovered_episodes = set()
        for ep in parsed_data.get("episodes", []):
            m = re.search(r"\d+", str(ep.get("episode", "")))
            if m:
                discovered_episodes.add(int(m.group()))
        if r_dir.exists():
            for p in r_dir.glob("candidates_episode*.json"):
                m = re.search(r"candidates_episode(\d+)\.json", p.name)
                if m:
                    discovered_episodes.add(int(m.group(1)))
        episode_numbers = sorted(discovered_episodes)

    all_layer1_selections = []
    all_candidates = []
    episodes_processed = 0

    for episode_number in episode_numbers:
        l1 = load_layer1_events(episode_number, event_lookup, raw_dir=r_dir)
        cands = load_evaluated_candidates(episode_number, raw_dir=r_dir)
        if cands:
            all_candidates.extend(cands)
            all_layer1_selections.extend(l1)
            episodes_processed += 1

    return {
        "episodes_processed": episodes_processed,
        "evaluated_candidates": all_candidates,
        "layer1_selections": all_layer1_selections,
        "screenplay_events": screenplay_events,
    }


if __name__ == "__main__":
    data = load_promo_composer_data()

    print("\n========== PROMO COMPOSER INPUT SUMMARY ==========")
    print(f"Episodes processed: {data['episodes_processed']}")
    print(f"Evaluated candidates: {len(data['evaluated_candidates'])}")
    print(f"Layer 1 selections: {len(data['layer1_selections'])}")
    print(f"Total screenplay events: {len(data['screenplay_events'])}")

    selected_count = sum(
        event["layer1_selected"]
        for event in data["screenplay_events"]
    )

    print(f"Events identified by Layer 1: {selected_count}")
    print(
        f"Additional screenplay events: "
        f"{len(data['screenplay_events']) - selected_count}"
    )
    print("==================================================")
