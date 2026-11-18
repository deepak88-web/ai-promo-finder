
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "outputs" / "raw"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"

SCORE_FIELDS = [
    "opening_hook",
    "emotional_impact",
    "suspense_curiosity",
    "narrative_coherence",
    "promotional_value",
    "ending_strength",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def join_list(value):
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return value


def consolidate_results(raw_dir=None, report_dir=None):
    import re

    r_dir = Path(raw_dir) if raw_dir else RAW_DIR
    rep_dir = Path(report_dir) if report_dir else REPORT_DIR
    rep_dir.mkdir(parents=True, exist_ok=True)

    master_records = []
    episode_records = []
    warnings = []

    # Discover available episodes dynamically
    discovered_episodes = set()
    if r_dir.exists():
        for p in r_dir.glob("candidates_episode*.json"):
            m = re.search(r"candidates_episode(\d+)\.json", p.name)
            if m:
                discovered_episodes.add(int(m.group(1)))

    episode_numbers = sorted(discovered_episodes) if discovered_episodes else list(range(1, 51))

    for episode_number in episode_numbers:
        episode_id = f"EP{episode_number:03d}"

        candidate_path = (
            r_dir / f"candidates_episode{episode_number}.json"
        )
        evaluation_path = (
            r_dir / f"layer2_episode{episode_number}_evaluation.json"
        )

        if not candidate_path.exists():
            warnings.append(f"{episode_id}: Candidate file missing")
            continue

        if not evaluation_path.exists():
            warnings.append(f"{episode_id}: Evaluation file missing")
            continue

        try:
            candidate_data = load_json(candidate_path)
            evaluation_data = load_json(evaluation_path)
        except (json.JSONDecodeError, OSError) as error:
            warnings.append(f"{episode_id}: Could not read JSON: {error}")
            continue

        candidates = candidate_data.get("candidates", [])
        evaluations = evaluation_data.get("evaluated_candidates", [])

        evaluation_lookup = {}

        for evaluation in evaluations:
            candidate_id = evaluation.get("candidate_id")
            if candidate_id:
                if candidate_id in evaluation_lookup:
                    warnings.append(
                        f"{episode_id}: Duplicate evaluation for {candidate_id}"
                    )
                evaluation_lookup[candidate_id] = evaluation

        episode_rows = []

        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")

            if not candidate_id:
                warnings.append(f"{episode_id}: Candidate without candidate_id")
                continue

            evaluation = evaluation_lookup.get(candidate_id, {})
            scores = evaluation.get("scores", {})

            record = {
                "episode": episode_id,
                "candidate_id": candidate_id,
                "scene_number": candidate.get("scene_number"),
                "start_time": candidate.get("start_time"),
                "end_time": candidate.get("end_time"),
                "duration": candidate.get("duration"),
                "selection_ids": join_list(candidate.get("selection_ids", [])),
                "event_ids": join_list(candidate.get("event_ids", [])),
                "event_categories": join_list(
                    candidate.get("event_categories", [])
                ),
                "descriptions": join_list(candidate.get("descriptions", [])),
                "importance": candidate.get("importance"),
                "weighted_score": evaluation.get("weighted_score"),
                "strengths": join_list(evaluation.get("strengths", [])),
                "weaknesses": join_list(evaluation.get("weaknesses", [])),
                "overall_assessment": evaluation.get("overall_assessment"),
                "evaluation_status": (
                    "Evaluated" if evaluation else "Not evaluated"
                ),
            }

            for field in SCORE_FIELDS:
                record[field] = scores.get(field)

            master_records.append(record)
            episode_rows.append(record)

        evaluated_rows = [
            row for row in episode_rows
            if row["weighted_score"] is not None
        ]

        evaluated_rows.sort(
            key=lambda row: row["weighted_score"],
            reverse=True
        )

        best = evaluated_rows[0] if evaluated_rows else None

        episode_records.append({
            "episode": episode_id,
            "candidate_count": len(candidates),
            "evaluated_count": len(evaluated_rows),
            "best_candidate": best["candidate_id"] if best else None,
            "best_score": best["weighted_score"] if best else None,
            "best_start_time": best["start_time"] if best else None,
            "best_end_time": best["end_time"] if best else None,
            "best_duration": best["duration"] if best else None,
        })

    if not master_records:
        print("No candidate records found. Check the input files.")
        return

    master_df = pd.DataFrame(master_records)

    # Global ranking across all episodes
    ranked_df = master_df[
        master_df["weighted_score"].notna()
    ].copy()

    ranked_df = ranked_df.sort_values(
        by=["weighted_score", "candidate_id"],
        ascending=[False, True]
    ).reset_index(drop=True)

    ranked_df.insert(0, "global_rank", range(1, len(ranked_df) + 1))

    # Episode-wise summary
    episode_df = pd.DataFrame(episode_records)

    master_path = rep_dir / "master_candidate_results.csv"
    ranking_path = rep_dir / "global_ranking.csv"
    summary_path = rep_dir / "episode_summary.csv"

    master_df.to_csv(master_path, index=False)
    ranked_df.to_csv(ranking_path, index=False)
    episode_df.to_csv(summary_path, index=False)

    print("\n===== CONSOLIDATION COMPLETE =====")
    print(f"Total candidates: {len(master_df)}")
    print(f"Evaluated candidates: {len(ranked_df)}")
    print(f"Episodes included: {len(episode_df)}")

    print("\nTop 10 candidates:")
    print(
        ranked_df[
            ["global_rank", "episode", "candidate_id", "weighted_score"]
        ].head(10).to_string(index=False)
    )

    print("\nGenerated reports:")
    print(master_path)
    print(ranking_path)
    print(summary_path)

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print("-", warning)
    else:
        print("\nNo missing-file or JSON-read warnings.")

    return {
        "master_report": master_path,
        "ranking_report": ranking_path,
        "summary_report": summary_path,
    }


if __name__ == "__main__":
    consolidate_results()
