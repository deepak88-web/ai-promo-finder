
import re
import json
import zipfile
from pathlib import Path


# --------------------------------------------------
# 1. Timestamp conversion
# --------------------------------------------------

def to_seconds(timestamp):
    minutes, rest = timestamp.split(":")
    seconds, hundredths = rest.split(".")

    return (
        int(minutes) * 60
        + int(seconds)
        + int(hundredths) / 100
    )


# --------------------------------------------------
# 2. Event pattern
# --------------------------------------------------

EVENT_PATTERN = re.compile(
    r"^\*\*(?P<header>[^*\n]+):\*\*\s*\n"
    r"\s*Start:\s*\((?P<start>\d{2}:\d{2}\.\d{2})\)"
    r"\s*\|\s*End:\s*\((?P<end>\d{2}:\d{2}\.\d{2})\)\s*\n"
    r"(?P<body>.*?)"
    r"(?=^\*\*[^*\n]+:\*\*\s*$"
    r"|^SCENE\s+\d+\b"
    r"|^---\s*SCRIPT END\s*---"
    r"|\Z)",
    re.MULTILINE | re.DOTALL
)


# --------------------------------------------------
# 3. Parse event header
# --------------------------------------------------

DELIVERY_MARKERS = {
    "O.S.": "O.S.",
    "V.O.": "V.O.",
    "O.C.": "O.C.",
    "OFF-SCREEN": "O.S.",
    "VOICE OVER": "V.O.",
    "CONT'D": "CONT'D",
    "CONTINUED": "CONTINUED"
}


def parse_header(header):
    header = header.strip()

    # Non-dialogue event types
    if header.upper() in ("CAMERA", "ACTION", "SOUND FX"):
        return {
            "type": header.lower().replace(" ", "_"),
            "speaker": None,
            "tone": None,
            "delivery": None
        }

    # Extract the speaker name before the first parenthesis
    first_parenthesis = header.find("(")

    if first_parenthesis == -1:
        speaker = header.strip()
        annotations = []
    else:
        speaker = header[:first_parenthesis].strip()

        annotation_text = header[first_parenthesis:]

        annotations = re.findall(
            r"\(([^()]*)\)",
            annotation_text
        )

    tones = []
    deliveries = []

    for annotation in annotations:
        remaining = annotation.strip()

        # Identify delivery markers inside annotations
        for marker, normalized in DELIVERY_MARKERS.items():
            pattern = re.compile(
                r"(?<![A-Z])" + re.escape(marker) + r"(?![A-Z])",
                re.IGNORECASE
            )

            if pattern.search(remaining):
                deliveries.append(normalized)
                remaining = pattern.sub("", remaining)

        remaining = re.sub(r"\s*[,/]\s*", " ", remaining)
        remaining = remaining.strip(" ,/")

        if remaining:
            tones.append(remaining)

    return {
        "type": "dialogue",
        "speaker": speaker,
        "tone": ", ".join(tones) if tones else None,
        "delivery": ", ".join(dict.fromkeys(deliveries)) if deliveries else None
    }


# --------------------------------------------------
# 4. Parse one event
# --------------------------------------------------

def parse_events(scene_text, episode_number, scene_number):
    events = []

    for match in EVENT_PATTERN.finditer(scene_text):
        header = match.group("header").strip()

        body = match.group("body").strip()

        # Remove screenplay ending markers if present
        body = re.sub(
            r"\n*\s*---\s*SCRIPT END\s*---\s*$",
            "",
            body,
            flags=re.IGNORECASE
        ).strip()

        if not body:
            continue

        event_info = parse_header(header)

        start_timestamp = match.group("start")
        end_timestamp = match.group("end")

        events.append({
            "episode": episode_number,
            "scene_number": scene_number,
            **event_info,
            "start_time": to_seconds(start_timestamp),
            "end_time": to_seconds(end_timestamp),
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "text": body
        })

    return events


# --------------------------------------------------
# 5. Parse one scene
# --------------------------------------------------

def parse_scene(scene_text, episode_number):

    scene_match = re.search(
        r"^SCENE\s+(\d+)\b",
        scene_text,
        re.MULTILINE | re.IGNORECASE
    )

    if not scene_match:
        return None

    scene_number = int(scene_match.group(1))

    # Case-insensitive metadata matching
    heading_match = re.search(
        r"^SCENE HEADING:\s*(.+)$",
        scene_text,
        re.MULTILINE | re.IGNORECASE
    )

    start_match = re.search(
        r"^SCENE START:\s*(\d{2}:\d{2}\.\d{2})",
        scene_text,
        re.MULTILINE | re.IGNORECASE
    )

    end_match = re.search(
        r"^SCENE END:\s*(\d{2}:\d{2}\.\d{2})",
        scene_text,
        re.MULTILINE | re.IGNORECASE
    )

    scene_start = (
        to_seconds(start_match.group(1))
        if start_match else None
    )

    scene_end = (
        to_seconds(end_match.group(1))
        if end_match else None
    )

    events = parse_events(
        scene_text,
        episode_number,
        scene_number
    )

    return {
        "scene_number": scene_number,
        "scene_heading": (
            heading_match.group(1).strip()
            if heading_match else None
        ),
        "scene_start": scene_start,
        "scene_end": scene_end,
        "events": events
    }


# --------------------------------------------------
# 6. Parse one episode
# --------------------------------------------------

def parse_episode(filename, content):

    episode_match = re.search(
        r"^EPISODE NUMBER:\s*(.+)$",
        content,
        re.MULTILINE | re.IGNORECASE
    )

    logline_match = re.search(
        r"^EPISODE LOGLINE:\s*(.+)$",
        content,
        re.MULTILINE | re.IGNORECASE
    )

    continuity_match = re.search(
        r"^CONTINUITY NOTES:\s*(.+)$",
        content,
        re.MULTILINE | re.IGNORECASE
    )

    episode_number = (
        episode_match.group(1).strip()
        if episode_match
        else Path(filename).stem
    )

    # Extract only the screenplay section
    script_match = re.search(
        r"---\s*SCRIPT START\s*---(.*?)(?:---\s*SCRIPT END\s*---|\Z)",
        content,
        re.DOTALL | re.IGNORECASE
    )

    if not script_match:
        return None

    script = script_match.group(1)

    # Split screenplay into individual scenes
    scene_sections = re.split(
        r"(?=^SCENE\s+\d+\b)",
        script,
        flags=re.MULTILINE | re.IGNORECASE
    )

    scenes = []

    for section in scene_sections:
        if re.match(
            r"^\s*SCENE\s+\d+\b",
            section,
            re.IGNORECASE
        ):
            scene = parse_scene(section, episode_number)

            if scene:
                scenes.append(scene)

    return {
        "filename": Path(filename).name,
        "episode": episode_number,
        "logline": (
            logline_match.group(1).strip()
            if logline_match else None
        ),
        "continuity_notes": (
            continuity_match.group(1).strip()
            if continuity_match else None
        ),
        "scenes": scenes
    }


# --------------------------------------------------
# 7. Validate parsed episodes
# --------------------------------------------------

def validate_episodes(episodes):

    warnings = []

    for episode in episodes:
        episode_number = episode["episode"]

        for scene in episode["scenes"]:
            scene_start = scene["scene_start"]
            scene_end = scene["scene_end"]

            if scene_start is None or scene_end is None:
                warnings.append({
                    "episode": episode_number,
                    "scene": scene["scene_number"],
                    "issue": "Missing scene boundary metadata"
                })
                continue

            if scene_start > scene_end:
                warnings.append({
                    "episode": episode_number,
                    "scene": scene["scene_number"],
                    "issue": "Scene start is after scene end"
                })

            for event in scene["events"]:

                if event["start_time"] > event["end_time"]:
                    warnings.append({
                        "episode": episode_number,
                        "scene": scene["scene_number"],
                        "issue": "Event has reversed timestamps",
                        "event": event["text"]
                    })

                if (
                    event["start_time"] < scene_start
                    or event["end_time"] > scene_end
                ):
                    warnings.append({
                        "episode": episode_number,
                        "scene": scene["scene_number"],
                        "issue": "Event extends beyond scene boundaries",
                        "event_start": event["start_timestamp"],
                        "event_end": event["end_timestamp"],
                        "scene_start": scene_start,
                        "scene_end": scene_end
                    })

    return warnings


# --------------------------------------------------
# 8. Parse all TXT files
# --------------------------------------------------

def main():

    zip_files = sorted(Path("data/raw").glob("*.zip"))

    if not zip_files:
        raise FileNotFoundError(
            "No ZIP file found inside data/raw"
        )

    if len(zip_files) > 1:
        print("Multiple ZIP files found. Using:", zip_files[0].name)

    zip_path = zip_files[0]

    parsed_episodes = []

    with zipfile.ZipFile(zip_path, "r") as archive:

        txt_files = sorted(
            name for name in archive.namelist()
            if name.lower().endswith(".txt")
        )

        for filename in txt_files:

            content = archive.read(filename).decode(
                "utf-8-sig",
                errors="replace"
            )

            episode = parse_episode(filename, content)

            if episode:
                parsed_episodes.append(episode)

    # Event counts
    all_events = [
        event
        for episode in parsed_episodes
        for scene in episode["scenes"]
        for event in scene["events"]
    ]

    event_counts = {
        event_type: sum(
            1 for event in all_events
            if event["type"] == event_type
        )
        for event_type in (
            "dialogue",
            "camera",
            "action",
            "sound_fx"
        )
    }

    # Validation
    warnings = validate_episodes(parsed_episodes)

    output = {
        "summary": {
            "total_episodes": len(parsed_episodes),
            "total_scenes": sum(
                len(episode["scenes"])
                for episode in parsed_episodes
            ),
            "total_events": len(all_events),
            "dialogue_events": event_counts["dialogue"],
            "camera_events": event_counts["camera"],
            "action_events": event_counts["action"],
            "sound_fx_events": event_counts["sound_fx"],
            "validation_warnings": len(warnings)
        },
        "validation_warnings": warnings,
        "episodes": parsed_episodes
    }

    # Save parsed JSON
    output_path = Path(
        "data/interim/parsed_episodes.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(
            output,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # Print summary
    print("\n===== PARSING SUMMARY =====")

    for key, value in output["summary"].items():
        print(f"{key}: {value}")

    print("\nParsed data saved at:", output_path)

    if warnings:
        print("\n===== VALIDATION WARNINGS =====")

        for warning in warnings[:20]:
            print(warning)

        if len(warnings) > 20:
            print(
                f"... and {len(warnings) - 20} more warnings."
            )
    else:
        print("\nNo validation warnings found.")


if __name__ == "__main__":
    main()
