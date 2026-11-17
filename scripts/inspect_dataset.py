
import zipfile
import re
import json
from pathlib import Path
from collections import Counter
from statistics import mean

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = PROJECT_ROOT / "data" / "raw" / "screenplay_dataset.zip"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_episode(filename, content):

    # Extract episode number
    episode_match = re.search(
        r"EPISODE NUMBER:\s*(.+)",
        content,
        re.IGNORECASE
    )

    episode_number = (
        episode_match.group(1).strip()
        if episode_match else None
    )

    # Count scenes
    scenes = re.findall(
        r"^SCENE\s+\d+",
        content,
        re.MULTILINE | re.IGNORECASE
    )

    # Count timestamp entries
    timestamps = re.findall(
        r"\b\d{2}:\d{2}\.\d{2}\b",
        content
    )

    # Count dialogues
    dialogues = re.findall(
        r"^[A-Z][A-Z\s.'-]+(?:\s*\([^)]*\))?:\s*$",
        content,
        re.MULTILINE
    )

    # Count actions and camera directions
    action_count = len(re.findall(
        r"^\*\*ACTION:\*\*",
        content,
        re.MULTILINE
    ))

    camera_count = len(re.findall(
        r"^\*\*CAMERA:\*\*",
        content,
        re.MULTILINE
    ))

    # Check required sections
    has_logline = bool(re.search(
        r"EPISODE LOGLINE:",
        content
    ))

    has_continuity = bool(re.search(
        r"CONTINUITY NOTES:",
        content
    ))

    has_script_start = bool(re.search(
        r"--- SCRIPT START ---",
        content
    ))

    return {
        "filename": filename,
        "episode_number": episode_number,
        "characters_count": len(content),
        "scene_count": len(scenes),
        "timestamp_count": len(timestamps),
        "dialogue_headers": len(dialogues),
        "action_blocks": action_count,
        "camera_blocks": camera_count,
        "has_logline": has_logline,
        "has_continuity": has_continuity,
        "has_script_start": has_script_start
    }


def main():

    if not ZIP_PATH.exists():
        print(f"ZIP file not found: {ZIP_PATH}")
        return

    episode_reports = []

    with zipfile.ZipFile(ZIP_PATH, "r") as archive:

        txt_files = [
            name for name in archive.namelist()
            if name.lower().endswith(".txt")
        ]

        print(f"Total TXT files found: {len(txt_files)}")

        for filename in txt_files:

            content = archive.read(filename).decode(
                "utf-8-sig",
                errors="replace"
            )

            report = inspect_episode(filename, content)
            episode_reports.append(report)

    # Dataset-level statistics
    scene_counts = [
        item["scene_count"] for item in episode_reports
    ]

    timestamp_counts = [
        item["timestamp_count"] for item in episode_reports
    ]

    dataset_summary = {
        "total_episodes": len(episode_reports),
        "total_scenes": sum(scene_counts),
        "average_scenes_per_episode": round(mean(scene_counts), 2)
            if scene_counts else 0,
        "average_timestamps_per_episode": round(mean(timestamp_counts), 2)
            if timestamp_counts else 0,
        "min_timestamps": min(timestamp_counts)
            if timestamp_counts else 0,
        "max_timestamps": max(timestamp_counts)
            if timestamp_counts else 0
    }

    final_report = {
        "dataset_summary": dataset_summary,
        "episode_reports": episode_reports
    }

    # Save JSON report
    output_path = OUTPUT_DIR / "dataset_inspection.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            final_report,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Display summary
    print("\n===== DATASET INSPECTION =====")

    for key, value in dataset_summary.items():
        print(f"{key}: {value}")

    print("\n===== EPISODE DETAILS =====")

    for episode in episode_reports:
        print(
            episode["episode_number"],
            "| Scenes:", episode["scene_count"],
            "| Timestamps:", episode["timestamp_count"],
            "| Dialogues:", episode["dialogue_headers"]
        )

    print(f"\nReport saved at: {output_path}")


if __name__ == "__main__":
    main()

import zipfile
import re
import json
from pathlib import Path
from collections import Counter
from statistics import mean

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = PROJECT_ROOT / "data" / "raw" / "screenplay_dataset.zip"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_episode(filename, content):

    # Extract episode number
    episode_match = re.search(
        r"EPISODE NUMBER:\s*(.+)",
        content,
        re.IGNORECASE
    )

    episode_number = (
        episode_match.group(1).strip()
        if episode_match else None
    )

    # Count scenes
    scenes = re.findall(
        r"^SCENE\s+\d+",
        content,
        re.MULTILINE | re.IGNORECASE
    )

    # Count timestamp entries
    timestamps = re.findall(
        r"\b\d{2}:\d{2}\.\d{2}\b",
        content
    )

    # Count dialogues
    dialogues = re.findall(
        r"^\*\*[A-Z][A-Z\s.'-]+(?:\s*\([^)]*\))?:\*\*$",
        content,
        re.MULTILINE
    )

    # Count actions and camera directions
    action_count = len(re.findall(
        r"^\*\*ACTION:\*\*",
        content,
        re.MULTILINE
    ))

    camera_count = len(re.findall(
        r"^\*\*CAMERA:\*\*",
        content,
        re.MULTILINE
    ))

    # Check required sections
    has_logline = bool(re.search(
        r"EPISODE LOGLINE:",
        content
    ))

    has_continuity = bool(re.search(
        r"CONTINUITY NOTES:",
        content
    ))

    has_script_start = bool(re.search(
        r"--- SCRIPT START ---",
        content
    ))

    return {
        "filename": filename,
        "episode_number": episode_number,
        "characters_count": len(content),
        "scene_count": len(scenes),
        "timestamp_count": len(timestamps),
        "dialogue_headers": len(dialogues),
        "action_blocks": action_count,
        "camera_blocks": camera_count,
        "has_logline": has_logline,
        "has_continuity": has_continuity,
        "has_script_start": has_script_start
    }


def main():

    if not ZIP_PATH.exists():
        print(f"ZIP file not found: {ZIP_PATH}")
        return

    episode_reports = []

    with zipfile.ZipFile(ZIP_PATH, "r") as archive:

        txt_files = [
            name for name in archive.namelist()
            if name.lower().endswith(".txt")
        ]

        print(f"Total TXT files found: {len(txt_files)}")

        for filename in txt_files:

            content = archive.read(filename).decode(
                "utf-8-sig",
                errors="replace"
            )

            report = inspect_episode(filename, content)
            episode_reports.append(report)

    # Dataset-level statistics
    scene_counts = [
        item["scene_count"] for item in episode_reports
    ]

    timestamp_counts = [
        item["timestamp_count"] for item in episode_reports
    ]

    dataset_summary = {
        "total_episodes": len(episode_reports),
        "total_scenes": sum(scene_counts),
        "average_scenes_per_episode": round(mean(scene_counts), 2)
            if scene_counts else 0,
        "average_timestamps_per_episode": round(mean(timestamp_counts), 2)
            if timestamp_counts else 0,
        "min_timestamps": min(timestamp_counts)
            if timestamp_counts else 0,
        "max_timestamps": max(timestamp_counts)
            if timestamp_counts else 0
    }

    final_report = {
        "dataset_summary": dataset_summary,
        "episode_reports": episode_reports
    }

    # Save JSON report
    output_path = OUTPUT_DIR / "dataset_inspection.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            final_report,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Display summary
    print("\n===== DATASET INSPECTION =====")

    for key, value in dataset_summary.items():
        print(f"{key}: {value}")

    print("\n===== EPISODE DETAILS =====")

    for episode in episode_reports:
        print(
            episode["episode_number"],
            "| Scenes:", episode["scene_count"],
            "| Timestamps:", episode["timestamp_count"],
            "| Dialogues:", episode["dialogue_headers"]
        )

    print(f"\nReport saved at: {output_path}")


if __name__ == "__main__":
    main()
