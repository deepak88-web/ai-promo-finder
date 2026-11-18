
import argparse
import json
import re
from pathlib import Path

from src.llm.provider_router import get_provider


# --------------------------------------------------
# 1. Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "data" / "interim" / "parsed_episodes.json"
)

PROMPT_PATH = (
    PROJECT_ROOT / "src" / "llm" / "prompts"
    / "event_identification.txt"
)
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
RAW_DIR = PROJECT_ROOT / "outputs" / "raw"


# --------------------------------------------------
# 2. Episode identification and output paths
# --------------------------------------------------

def get_episode_number(episode_name):
    """Extract the episode number from an episode name."""

    match = re.search(r"(\d+)", str(episode_name))

    if not match:
        raise ValueError(
            f"Could not extract episode number: {episode_name}"
        )

    return int(match.group(1))


def get_episode_id(episode_name):
    """Convert Episode 22 into EP022."""

    return f"EP{get_episode_number(episode_name):03d}"


def get_output_paths(episode_number, reports_dir=REPORT_DIR, raw_dir=RAW_DIR):
    """Create episode-specific input and result file paths."""

    input_output_path = (
        Path(reports_dir)
        / f"layer1_episode{episode_number}_input.json"
    )

    result_output_path = (
        Path(raw_dir)
        / f"layer1_episode{episode_number}_events.json"
    )

    return input_output_path, result_output_path


# --------------------------------------------------
# 3. Generate stable IDs
# --------------------------------------------------

def assign_event_ids(episode):

    episode_id = get_episode_id(episode["episode"])

    episode["episode_id"] = episode_id

    for scene in episode["scenes"]:

        scene_id = (
            f"{episode_id}_S{scene['scene_number']:03d}"
        )

        scene["scene_id"] = scene_id

        for index, event in enumerate(
            scene["events"], start=1
        ):

            event["event_id"] = (
                f"{scene_id}_E{index:03d}"
            )

    return episode


# --------------------------------------------------
# 4. Prepare one complete episode for the LLM
# --------------------------------------------------

def prepare_episode_input(episode):

    formatted_scenes = []

    for scene in episode["scenes"]:

        formatted_events = []

        for event in scene["events"]:

            formatted_events.append({
                "event_id": event["event_id"],
                "type": event["type"],
                "speaker": event["speaker"],
                "tone": event["tone"],
                "delivery": event.get("delivery"),
                "start_timestamp": event["start_timestamp"],
                "end_timestamp": event["end_timestamp"],
                "text": event["text"]
            })

        formatted_scenes.append({
            "scene_id": scene["scene_id"],
            "scene_number": scene["scene_number"],
            "scene_heading": scene["scene_heading"],
            "scene_start": scene["scene_start"],
            "scene_end": scene["scene_end"],
            "events": formatted_events
        })

    return {
        "episode": episode["episode"],
        "episode_id": episode["episode_id"],
        "logline": episode["logline"],
        "continuity_notes": episode["continuity_notes"],
        "scenes": formatted_scenes
    }


# --------------------------------------------------
# 5. Load prompt
# --------------------------------------------------

def load_prompt():

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {PROMPT_PATH}"
        )

    return PROMPT_PATH.read_text(encoding="utf-8")


# --------------------------------------------------
# 6. Build LLM request
# --------------------------------------------------

def build_layer1_request(episode):

    prompt = load_prompt()

    episode_data = prepare_episode_input(episode)

    # Compact JSON reduces unnecessary whitespace.
    user_input = (
        "Analyze the following screenplay episode.\n\n"
        "Return the required JSON output only.\n\n"
        "SCREENPLAY DATA:\n"
        + json.dumps(
            episode_data,
            ensure_ascii=False,
            separators=(",", ":")
        )
    )

    return {
        "system_prompt": prompt,
        "user_input": user_input
    }


# --------------------------------------------------
# 7. Load parsed episodes
# --------------------------------------------------

def load_episodes(input_path=INPUT_PATH):
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Parsed screenplay data not found: {input_path}"
        )

    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    episodes = data.get("episodes", [])

    if not episodes:
        raise ValueError(
            "No episodes found in parsed JSON."
        )

    return episodes


def find_episode(episodes, episode_number):
    """Find an episode using its numeric identifier."""

    for episode in episodes:

        current_number = get_episode_number(
            episode["episode"]
        )

        if current_number == episode_number:
            return episode

    raise ValueError(
        f"Episode {episode_number} was not found "
        "in parsed screenplay data."
    )


# --------------------------------------------------
# 8. Validate Layer 1 response
# --------------------------------------------------

def validate_layer1_response(result, episode):

    if not isinstance(result, dict):
        raise ValueError(
            "Model response must be a JSON object."
        )

    expected_episode_id = get_episode_id(
        episode["episode"]
    )

    received_episode_id = str(
        result.get("episode", "")
    ).strip()

    if received_episode_id != expected_episode_id:
        raise ValueError(
            f"Incorrect episode identifier. "
            f"Expected: {expected_episode_id}, "
            f"Received: {received_episode_id}"
        )

    dramatic_events = result.get("dramatic_events")

    if not isinstance(dramatic_events, list):
        raise ValueError(
            "dramatic_events must be a list."
        )

    valid_event_ids = {
        event["event_id"]
        for scene in episode["scenes"]
        for event in scene["events"]
    }

    # Preserve original event order for chronology checks.
    event_order = {
        event["event_id"]: index
        for index, event in enumerate(
            event
            for scene in episode["scenes"]
            for event in scene["events"]
        )
    }

    allowed_categories = {
        "revelation",
        "confrontation",
        "emotional",
        "romantic",
        "suspense",
        "cliffhanger",
        "character_decision",
        "powerful_dialogue"
    }

    allowed_potential = {
        "strong",
        "medium",
        "weak"
    }

    selection_ids = set()

    required_fields = {
        "selection_id",
        "event_ids",
        "event_category",
        "importance",
        "emotional_tone",
        "description",
        "promotional_reason",
        "hook_potential",
        "ending_potential",
        "requires_context"
    }

    for selection in dramatic_events:

        if not isinstance(selection, dict):
            raise ValueError(
                "Each dramatic event must be a JSON object."
            )

        missing = required_fields - selection.keys()

        if missing:
            raise ValueError(
                f"Missing fields in selection: {missing}"
            )

        # Check selection ID.
        selection_id = selection["selection_id"]

        if (
            not isinstance(selection_id, str)
            or not selection_id
        ):
            raise ValueError("Invalid selection_id.")

        if selection_id in selection_ids:
            raise ValueError(
                f"Duplicate selection_id: {selection_id}"
            )

        selection_ids.add(selection_id)

        # Check event IDs.
        selected_ids = selection["event_ids"]

        if (
            not isinstance(selected_ids, list)
            or not selected_ids
            or not all(
                isinstance(x, str) for x in selected_ids
            )
        ):
            raise ValueError(
                f"Invalid event_ids in {selection_id}."
            )

        unknown_ids = set(selected_ids) - valid_event_ids

        if unknown_ids:
            raise ValueError(
                f"Unknown event IDs returned: {unknown_ids}"
            )

        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError(
                f"Duplicate event IDs in {selection_id}."
            )

        # Check chronological order.
        positions = [
            event_order[event_id]
            for event_id in selected_ids
        ]

        if positions != sorted(positions):
            raise ValueError(
                f"Events are not in chronological order "
                f"in {selection_id}."
            )

        # Check category.
        if selection["event_category"] not in allowed_categories:
            raise ValueError(
                f"Invalid event category in {selection_id}."
            )

        # Check importance.
        importance = selection["importance"]

        if (
            isinstance(importance, bool)
            or not isinstance(importance, int)
            or importance not in range(1, 6)
        ):
            raise ValueError(
                f"Importance must be an integer from 1 to 5 "
                f"in {selection_id}."
            )

        # Check text fields.
        for field in (
            "emotional_tone",
            "description",
            "promotional_reason"
        ):

            if (
                not isinstance(selection[field], str)
                or not selection[field].strip()
            ):
                raise ValueError(
                    f"Invalid {field} in {selection_id}."
                )

        # Check hook and ending potential.
        if selection["hook_potential"] not in allowed_potential:
            raise ValueError(
                f"Invalid hook_potential in {selection_id}."
            )

        if selection["ending_potential"] not in allowed_potential:
            raise ValueError(
                f"Invalid ending_potential in {selection_id}."
            )

        # Check context requirement.
        if not isinstance(selection["requires_context"], bool):
            raise ValueError(
                f"requires_context must be boolean "
                f"in {selection_id}."
            )

    return True


# --------------------------------------------------
# 9. Save JSON output
# --------------------------------------------------

def save_json(data, output_path):

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(
            data,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# --------------------------------------------------
# 10. Run Layer 1 for a selected episode
# --------------------------------------------------

def run_layer1(episode_number=22, input_path=None, reports_dir=None, raw_dir=None,
               api_key=None, model=None, provider=None, base_url=None, parsed_path=None):

    actual_input = parsed_path or input_path or INPUT_PATH
    actual_reports = reports_dir or REPORT_DIR
    actual_raw = raw_dir or RAW_DIR

    input_output_path, result_output_path = (
        get_output_paths(episode_number, actual_reports, actual_raw)
    )

    # Load screenplay data.
    episodes = load_episodes(actual_input)

    # Find the requested episode.
    selected_episode = find_episode(
        episodes,
        episode_number
    )

    # Generate stable IDs.
    assign_event_ids(selected_episode)

    # Prepare the complete episode input.
    request = build_layer1_request(selected_episode)

    # Save the exact request for inspection.
    save_json(
        request,
        input_output_path
    )

    total_events = sum(
        len(scene["events"])
        for scene in selected_episode["scenes"]
    )

    episode_id = get_episode_id(
        selected_episode["episode"]
    )

    # Input size information.
    system_prompt_chars = len(request["system_prompt"])
    user_input_chars = len(request["user_input"])
    total_input_chars = (
        system_prompt_chars + user_input_chars
    )

    print("\n===== LAYER 1 INPUT PREPARATION =====")
    print("Episode:", selected_episode["episode"])
    print("Episode ID:", episode_id)
    print("Total scenes:", len(selected_episode["scenes"]))
    print("Total events:", total_events)

    print("\n===== REQUEST SIZE =====")
    print("System prompt characters:", system_prompt_chars)
    print("User input characters:", user_input_chars)
    print("Total characters:", total_input_chars)

    # Select the configured provider.
    provider_name, generate_json = get_provider("layer1", provider_override=provider)

    print(
        f"\nSending {selected_episode['episode']} "
        f"to {provider_name.upper()}..."
    )

    result = generate_json(
        system_prompt=request["system_prompt"],
        user_input=request["user_input"],
        api_key=api_key,
        model=model,
        base_url=base_url,
    )

    # Validate response.
    validate_layer1_response(
        result,
        selected_episode
    )

    # Save Layer 1 results.
    save_json(
        result,
        result_output_path
    )

    print("\n===== LAYER 1 RESULTS =====")
    print("Episode:", result["episode"])

    print(
        "Dramatic selections:",
        len(result["dramatic_events"])
    )

    print("Validation: Passed")
    print("Input saved at:", input_output_path)
    print("Results saved at:", result_output_path)

    return result


# --------------------------------------------------
# 11. Command-line execution
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Run Layer 1 dramatic event identification."
    )

    parser.add_argument(
        "--episode",
        type=int,
        default=22,
        help="Episode number to analyze (default: 22)."
    )

    args = parser.parse_args()

    if args.episode < 1:
        parser.error(
            "Episode number must be greater than zero."
        )

    run_layer1(args.episode)


if __name__ == "__main__":
    main()
