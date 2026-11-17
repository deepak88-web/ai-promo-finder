
import json
import re
from pathlib import Path

from src.llm.providers.gemini_provider import generate_json


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

INPUT_OUTPUT_PATH = (
    PROJECT_ROOT / "outputs" / "reports"
    / "layer1_episode22_input.json"
)

RESULT_OUTPUT_PATH = (
    PROJECT_ROOT / "outputs" / "raw"
    / "layer1_episode22_events.json"
)


# --------------------------------------------------
# 2. Generate stable IDs
# --------------------------------------------------

def get_episode_id(episode_name):

    match = re.search(r"(\d+)", episode_name)

    if not match:
        raise ValueError(
            f"Could not extract episode number: {episode_name}"
        )

    return f"EP{int(match.group(1)):03d}"


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
# 3. Prepare one episode for the LLM
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
# 4. Load prompt
# --------------------------------------------------

def load_prompt():

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {PROMPT_PATH}"
        )

    return PROMPT_PATH.read_text(encoding="utf-8")


# --------------------------------------------------
# 5. Build LLM request
# --------------------------------------------------

def build_layer1_request(episode):

    prompt = load_prompt()

    episode_data = prepare_episode_input(episode)

    user_input = (
        "Analyze the following screenplay episode.\n\n"
        "Return the required JSON output only.\n\n"
        "SCREENPLAY DATA:\n"
        + json.dumps(
            episode_data,
            indent=2,
            ensure_ascii=False
        )
    )

    return {
        "system_prompt": prompt,
        "user_input": user_input
    }


# --------------------------------------------------
# 6. Load parsed episodes
# --------------------------------------------------

def load_episodes():

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Parsed screenplay data not found: {INPUT_PATH}"
        )

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    episodes = data.get("episodes", [])

    if not episodes:
        raise ValueError(
            "No episodes found in parsed JSON."
        )

    return episodes


# --------------------------------------------------
# 7. Validate Layer 1 response
# --------------------------------------------------

def validate_layer1_response(result, episode):

    if not isinstance(result, dict):
        raise ValueError("Gemini response must be a JSON object.")

    expected_episode_id = get_episode_id(episode["episode"])

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

    # Preserve the original event order for chronology checks
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

        # Check selection ID
        selection_id = selection["selection_id"]

        if not isinstance(selection_id, str) or not selection_id:
            raise ValueError("Invalid selection_id.")

        if selection_id in selection_ids:
            raise ValueError(
                f"Duplicate selection_id: {selection_id}"
            )

        selection_ids.add(selection_id)

        # Check event IDs
        selected_ids = selection["event_ids"]

        if (
            not isinstance(selected_ids, list)
            or not selected_ids
            or not all(isinstance(x, str) for x in selected_ids)
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

        # Check chronological order
        positions = [
            event_order[event_id]
            for event_id in selected_ids
        ]

        if positions != sorted(positions):
            raise ValueError(
                f"Events are not in chronological order "
                f"in {selection_id}."
            )

        # Check category
        if selection["event_category"] not in allowed_categories:
            raise ValueError(
                f"Invalid event category in {selection_id}."
            )

        # Check importance
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

        # Check text fields
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

        # Check hook and ending potential
        if selection["hook_potential"] not in allowed_potential:
            raise ValueError(
                f"Invalid hook_potential in {selection_id}."
            )

        if selection["ending_potential"] not in allowed_potential:
            raise ValueError(
                f"Invalid ending_potential in {selection_id}."
            )

        # Check context requirement
        if not isinstance(selection["requires_context"], bool):
            raise ValueError(
                f"requires_context must be boolean "
                f"in {selection_id}."
            )

    return True


# --------------------------------------------------
# 8. Save JSON output
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
# 9. Main: Gemini Layer 1 execution
# --------------------------------------------------

def main():

    # Load screenplay data
    episodes = load_episodes()

    # Generate stable IDs
    for episode in episodes:
        assign_event_ids(episode)

    # Select Episode 22 for initial testing
    selected_episode = next(
        (
            episode for episode in episodes
            if episode["episode"] == "Episode 22"
        ),
        None
    )

    if selected_episode is None:
        raise ValueError(
            "Episode 22 was not found."
        )

    # Prepare input
    request = build_layer1_request(selected_episode)

    save_json(
        request,
        INPUT_OUTPUT_PATH
    )

    total_events = sum(
        len(scene["events"])
        for scene in selected_episode["scenes"]
    )

    print("\n===== LAYER 1 INPUT PREPARATION =====")
    print("Episode:", selected_episode["episode"])
    print("Episode ID:", selected_episode["episode_id"])
    print("Total scenes:", len(selected_episode["scenes"]))
    print("Total events:", total_events)

    # Call Gemini
    print("\nSending Episode 22 to Gemini...")

    result = generate_json(
        system_prompt=request["system_prompt"],
        user_input=request["user_input"]
    )

    # Validate response
    validate_layer1_response(
        result,
        selected_episode
    )

    # Save Gemini results
    save_json(
        result,
        RESULT_OUTPUT_PATH
    )

    # Display summary
    print("\n===== LAYER 1 GEMINI RESULTS =====")
    print("Episode:", result["episode"])
    print(
        "Dramatic selections:",
        len(result["dramatic_events"])
    )
    print("Validation: Passed")
    print("Input saved at:", INPUT_OUTPUT_PATH)
    print("Results saved at:", RESULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()
