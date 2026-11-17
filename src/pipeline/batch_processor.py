
import argparse
import csv
import json
import os
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

from src.llm.layer1_event_identification import run_layer1
from src.candidate_generation.candidate_generator import (
    run_candidate_generation
)
from src.llm.layer2_candidate_evaluation import (
    run_layer2_evaluation
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load project configuration explicitly.
load_dotenv(PROJECT_ROOT / ".env", override=True)

RAW_DIR = PROJECT_ROOT / "outputs" / "raw"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"

SUMMARY_PATH = REPORT_DIR / "batch_summary.csv"
PROGRESS_PATH = REPORT_DIR / "batch_progress.json"
FAILURES_PATH = REPORT_DIR / "batch_failures.json"


def load_json(path):
    """Load a JSON file."""

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path):
    """Save JSON data."""

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def load_failure_history():
    """Load failures from previous batch runs."""

    if not FAILURES_PATH.exists():
        return []

    try:
        data = load_json(FAILURES_PATH)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print("Warning: Could not read previous failure history.")
        return []


def save_progress(progress):
    """Save current batch progress."""

    save_json(progress, PROGRESS_PATH)


def save_failures(failures):
    """Save cumulative failure history."""

    save_json(failures, FAILURES_PATH)


def update_csv(row):
    """Append or update one episode in the summary CSV."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "episode",
        "layer1_provider",
        "layer2_provider",
        "dramatic_selections",
        "total_candidates",
        "valid_candidates",
        "best_candidate",
        "best_score",
        "status"
    ]

    existing_rows = []

    if SUMMARY_PATH.exists():
        with open(
            SUMMARY_PATH,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:
            reader = csv.DictReader(file)

            for item in reader:
                if item.get("episode"):
                    existing_rows.append(item)

    existing_rows = [
        item for item in existing_rows
        if item["episode"] != row["episode"]
    ]

    existing_rows.append(row)

    existing_rows.sort(
        key=lambda item: int(item["episode"].replace("EP", ""))
    )

    with open(
        SUMMARY_PATH,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)


def get_provider_settings():
    """Read providers from the project .env configuration."""

    return {
        "layer1": os.getenv("LAYER1_PROVIDER", "groq").strip().lower(),
        "layer2": os.getenv("LAYER2_PROVIDER", "groq").strip().lower()
    }


def process_episode(episode_number, force=False):
    """Run all three pipeline stages for one episode."""

    episode_id = f"EP{episode_number:03d}"

    layer1_path = (
        RAW_DIR / f"layer1_episode{episode_number}_events.json"
    )

    candidates_path = (
        RAW_DIR / f"candidates_episode{episode_number}.json"
    )

    layer2_path = (
        RAW_DIR / f"layer2_episode{episode_number}_evaluation.json"
    )

    print("\n" + "=" * 55)
    print(f"PROCESSING {episode_id}")
    print("=" * 55)

    layer1_ran = False
    candidates_ran = False

    # Stage 1: Layer 1
    if force or not layer1_path.exists():

        print("\n[1/3] Running Layer 1...")

        run_layer1(episode_number)
        layer1_ran = True

    else:
        print("\n[1/3] Layer 1 already completed. Skipping.")

    # Stage 2: Candidate generation
    if force or layer1_ran or not candidates_path.exists():

        print("\n[2/3] Generating candidates...")

        run_candidate_generation(episode_number)
        candidates_ran = True

    else:
        print("\n[2/3] Candidates already generated. Skipping.")

    # Stage 3: Layer 2
    if (
        force
        or layer1_ran
        or candidates_ran
        or not layer2_path.exists()
    ):

        print("\n[3/3] Running Layer 2 evaluation...")

        run_layer2_evaluation(episode_number)

    else:
        print("\n[3/3] Layer 2 already completed. Skipping.")

    # Confirm all expected output files exist.
    for path in [layer1_path, candidates_path, layer2_path]:
        if not path.exists():
            raise FileNotFoundError(
                f"Expected output was not created: {path}"
            )

    # Read final results.
    layer1_data = load_json(layer1_path)
    candidate_data = load_json(candidates_path)
    evaluation_data = load_json(layer2_path)

    best_candidate = evaluation_data["best_candidate"]

    best_score = next(
        item["weighted_score"]
        for item in evaluation_data["ranking"]
        if item["candidate_id"] == best_candidate
    )

    providers = get_provider_settings()

    return {
        "episode": episode_id,
        "layer1_provider": providers["layer1"],
        "layer2_provider": providers["layer2"],
        "dramatic_selections": len(
            layer1_data.get("dramatic_events", [])
        ),
        "total_candidates": candidate_data["summary"][
            "generated_candidates"
        ],
        "valid_candidates": candidate_data["summary"][
            "valid_candidates"
        ],
        "best_candidate": best_candidate,
        "best_score": best_score,
        "status": "completed"
    }


def is_daily_quota_error(error):
    """Identify Gemini daily request quota exhaustion."""

    message = str(error).lower()

    return (
        "daily api request quota exhausted" in message
        or (
            "requests per day" in message
            and "429" in message
        )
        or (
            "request per day" in message
            and "429" in message
        )
    )


def run_batch(start_episode=1, end_episode=50, force=False):
    """Process episodes and preserve progress and failure history."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    failures = load_failure_history()

    progress = {
        "started_at": datetime.now().isoformat(),
        "start_episode": start_episode,
        "end_episode": end_episode,
        "force": force,
        "completed": [],
        "failed": [],
        "status": "running"
    }

    quota_blocked = False

    print("\n===== AI PROMO FINDER BATCH PROCESSOR =====")
    print(f"Episodes: {start_episode} to {end_episode}")
    print(f"Force reprocessing: {force}")

    providers = get_provider_settings()

    print(f"Layer 1 provider: {providers['layer1'].upper()}")
    print(f"Layer 2 provider: {providers['layer2'].upper()}")

    for episode_number in range(start_episode, end_episode + 1):

        episode_id = f"EP{episode_number:03d}"

        try:
            result = process_episode(
                episode_number,
                force=force
            )

            update_csv(result)

            progress["completed"].append(episode_id)

            # Remove old failure records for a now-successful episode.
            failures = [
                item for item in failures
                if item.get("episode") != episode_id
            ]

            print(f"\n{episode_id} completed successfully.")

        except Exception as error:

            failure = {
                "episode": episode_id,
                "error": str(error),
                "failed_at": datetime.now().isoformat()
            }

            failures.append(failure)
            progress["failed"].append(failure)

            print(f"\nERROR processing {episode_id}: {error}")

            if is_daily_quota_error(error):
                quota_blocked = True

                print(
                    "\nDAILY GEMINI QUOTA EXHAUSTED."
                    "\nStopping the batch to avoid unnecessary API requests."
                )

        # Save progress after every episode.
        save_progress(progress)
        save_failures(failures)

        if quota_blocked:
            break

    progress["finished_at"] = datetime.now().isoformat()

    if quota_blocked:
        progress["status"] = "stopped_quota"

    elif progress["failed"]:
        progress["status"] = "completed_with_errors"

    else:
        progress["status"] = "completed"

    save_progress(progress)
    save_failures(failures)

    print("\n===== BATCH PROCESSING SUMMARY =====")
    print(f"Completed: {len(progress['completed'])}")
    print(f"Failed: {len(progress['failed'])}")

    if quota_blocked:
        print("Status: Stopped because of daily API quota exhaustion.")
    else:
        print(f"Status: {progress['status']}")

    print(f"\nCSV report: {SUMMARY_PATH}")
    print(f"Progress: {PROGRESS_PATH}")
    print(f"Failures: {FAILURES_PATH}")

    return progress


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Process AI Promo Finder episodes in batches."
    )

    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Starting episode number."
    )

    parser.add_argument(
        "--end",
        type=int,
        default=50,
        help="Ending episode number."
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess existing outputs."
    )

    args = parser.parse_args()

    if not (1 <= args.start <= 50):
        parser.error("Start episode must be between 1 and 50.")

    if not (args.start <= args.end <= 50):
        parser.error("End episode must be between start and 50.")

    run_batch(
        start_episode=args.start,
        end_episode=args.end,
        force=args.force
    )
