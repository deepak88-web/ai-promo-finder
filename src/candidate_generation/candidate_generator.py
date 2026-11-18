
import json
import argparse
import re
from pathlib import Path

from src.candidate_generation.event_analyzer import analyze_selections
from src.candidate_generation.window_generator import generate_candidate_windows
from src.candidate_generation.candidate_filter import filter_candidates


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PARSED_DATA_PATH = (
    PROJECT_ROOT / "data" / "interim" / "parsed_episodes.json"
)

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "raw"


def load_json(file_path):
    """Load JSON data from a file."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def find_episode(parsed_data, episode_id):
    """Find the requested episode in parsed screenplay data."""

    episode_number = int(episode_id[2:])

    for episode in parsed_data["episodes"]:
        match = re.search(r"\d+", str(episode.get("episode", "")))
        if match and int(match.group()) == episode_number:
            return episode

    raise ValueError(
        f"{episode_id} not found in parsed screenplay data."
    )


def run_candidate_generation(episode_number=22, parsed_data_path=PARSED_DATA_PATH, output_dir=OUTPUT_DIR):
    """Run candidate generation for the requested episode."""

    episode_id = f"EP{int(episode_number):03d}"

    layer1_results_path = (
        Path(output_dir) / f"layer1_episode{episode_number}_events.json"
    )

    output_path = (
        Path(output_dir) / f"candidates_episode{episode_number}.json"
    )

    print("\n===== CANDIDATE GENERATION PIPELINE =====")

    parsed_data = load_json(Path(parsed_data_path))
    layer1_result = load_json(layer1_results_path)

    if layer1_result.get("episode") != episode_id:
        raise ValueError(
            f"Expected {episode_id}, but Layer 1 result contains "
            f"{layer1_result.get('episode')}."
        )

    episode = find_episode(parsed_data, episode_id)

    print(f"Episode: {episode_id}")
    print("Step 1: Matching dramatic events...")

    analyzed_data = analyze_selections(
        layer1_result,
        episode
    )

    print(
        f"Matched selections: {len(analyzed_data['selections'])}"
    )

    print("Step 2: Generating candidate windows...")

    candidates = generate_candidate_windows(
        analyzed_data,
        episode,
        min_duration=20,
        max_duration=60,
        merge_gap=3
    )

    print(f"Generated windows: {len(candidates)}")

    print("Step 3: Validating candidate windows...")

    filter_result = filter_candidates(
        candidates,
        episode,
        min_duration=20,
        max_duration=60
    )

    valid_candidates = filter_result["valid_candidates"]

    output = {
        "episode": episode_id,
        "duration_constraints": {
            "minimum_seconds": 20,
            "maximum_seconds": 60
        },
        "summary": {
            "dramatic_selections": len(analyzed_data["selections"]),
            "generated_candidates": len(candidates),
            "valid_candidates": len(valid_candidates),
            "rejected_candidates": filter_result["total_rejected"]
        },
        "candidates": valid_candidates,
        "rejected_candidates": filter_result["rejected_candidates"]
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    print("\n===== CANDIDATE GENERATION RESULTS =====")
    print(f"Episode: {episode_id}")
    print(f"Generated: {len(candidates)}")
    print(f"Valid: {len(valid_candidates)}")
    print(f"Rejected: {filter_result['total_rejected']}")

    for candidate in valid_candidates:
        print(
            f"\n{candidate['candidate_id']}: "
            f"{candidate['start_time']}s - "
            f"{candidate['end_time']}s "
            f"({candidate['duration']} seconds)"
        )

    print(f"\nResults saved at: {output_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate promotional candidates for an episode."
    )

    parser.add_argument(
        "--episode",
        type=int,
        default=22,
        help="Episode number to process (default: 22)"
    )

    args = parser.parse_args()

    if args.episode < 1 or args.episode > 50:
        parser.error("Episode number must be between 1 and 50.")

    run_candidate_generation(args.episode)
