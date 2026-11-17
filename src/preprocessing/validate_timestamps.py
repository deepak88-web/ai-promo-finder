
import re
import json
import zipfile
from pathlib import Path

# Find the ZIP file inside data/raw
zip_files = list(Path("data/raw").glob("*.zip"))

if not zip_files:
    raise FileNotFoundError("No ZIP file found inside data/raw")

zip_path = zip_files[0]

# Matches event-level Start and End timestamps
event_pattern = re.compile(
    r"Start:\s*\((\d{2}:\d{2}\.\d{2})\)"
    r"\s*\|\s*End:\s*\((\d{2}:\d{2}\.\d{2})\)"
)

def to_seconds(timestamp):
    minutes, rest = timestamp.split(":")
    seconds, hundredths = rest.split(".")
    return int(minutes) * 60 + int(seconds) + int(hundredths) / 100

report = []

with zipfile.ZipFile(zip_path, "r") as archive:
    txt_files = [
        name for name in archive.namelist()
        if name.lower().endswith(".txt")
    ]

    for filename in txt_files:
        content = archive.read(filename).decode(
            "utf-8", errors="replace"
        )

        matches = event_pattern.findall(content)

        invalid_intervals = []

        for start, end in matches:
            if to_seconds(start) > to_seconds(end):
                invalid_intervals.append({
                    "start": start,
                    "end": end
                })

        report.append({
            "filename": filename,
            "timestamped_records": len(matches),
            "invalid_intervals": len(invalid_intervals),
            "invalid_examples": invalid_intervals[:5]
        })

total_records = sum(x["timestamped_records"] for x in report)
total_invalid = sum(x["invalid_intervals"] for x in report)

print("\n===== TIMESTAMP VALIDATION =====")
print("Episodes checked:", len(report))
print("Timestamped records:", total_records)
print("Invalid intervals:", total_invalid)

for item in report:
    print(
        f"{Path(item['filename']).name} | "
        f"Records: {item['timestamped_records']} | "
        f"Invalid: {item['invalid_intervals']}"
    )

output_path = Path("outputs/reports/timestamp_validation.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

output_path.write_text(
    json.dumps(report, indent=4),
    encoding="utf-8"
)

print("\nReport saved at:", output_path)
