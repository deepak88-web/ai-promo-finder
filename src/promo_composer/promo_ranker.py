
"""
Global Promo Ranker

Ranks evaluated promos using their six quality dimensions.
Does not make any LLM/API calls.
"""

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT_PATH = (
    PROJECT_ROOT / "outputs" / "raw" / "expanded" / "promo_evaluation.json"
    if (PROJECT_ROOT / "outputs" / "raw" / "expanded" / "promo_evaluation.json").exists()
    else PROJECT_ROOT / "outputs" / "raw" / "promo_evaluation.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "final"

# Weights sum to 1.0
WEIGHTS = {
    "opening_hook": 0.20,
    "standalone_coherence": 0.20,
    "narrative_flow": 0.15,
    "emotional_impact": 0.15,
    "cliffhanger_effectiveness": 0.20,
    "promotional_appeal": 0.10,
}

DECISION_ORDER = {
    "recommend": 0,
    "revise": 1,
    "reject": 2,
}


def format_seconds(val: float | None) -> str:
    """Format seconds into MM:SS.hh string."""
    if val is None:
        return "00:00.00"
    try:
        val = float(val)
        m = int(val // 60)
        s = val % 60
        return f"{m:02d}:{s:05.2f}"
    except (TypeError, ValueError):
        return "00:00.00"


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_score(
    evaluation: dict,
    criterion: str,
) -> float | None:
    """
    Read a criterion score from supported evaluation formats.

    Supports:
      scores.opening_hook
      opening_hook
      opening_hook_score
      criteria.opening_hook.score
    """

    aliases = [
        criterion,
        f"{criterion}_score",
    ]

    score_containers = [
        evaluation.get("scores"),
        evaluation.get("criteria"),
        evaluation,
    ]

    for container in score_containers:
        if not isinstance(container, dict):
            continue

        for alias in aliases:
            value = container.get(alias)

            if isinstance(value, dict):
                value = value.get("score")

            if isinstance(value, (int, float)):
                return max(0.0, min(10.0, float(value)))

    return None


def get_promo_id(item: dict) -> str:
    """Extract the promo identifier."""

    promo_id = item.get("promo_id")

    if not promo_id and isinstance(item.get("promo"), dict):
        promo_id = item["promo"].get("promo_id")

    if not promo_id:
        promo_id = item.get("id")

    return str(promo_id or "UNKNOWN")



def get_decision(item: dict) -> str:
    """Read recommendation from nested evaluation."""

    evaluation = item.get("evaluation", {})

    decision = evaluation.get("decision", "revise")

    decision = str(decision).strip().lower()

    if decision not in DECISION_ORDER:
        return "revise"

    return decision



def calculate_weighted_score(
    promo: dict,
) -> tuple[float, dict, list]:
    """
    Calculate weighted score from the nested evaluator output.
    """

    evaluation = promo.get("evaluation", {})

    if not isinstance(evaluation, dict) or not evaluation:
        raise ValueError(
            f"Missing nested evaluation for {get_promo_id(promo)}"
        )

    scores = {}
    missing = []

    for criterion in WEIGHTS:
        score = get_score(evaluation, criterion)

        if score is None:
            missing.append(criterion)
        else:
            scores[criterion] = score

    if missing:
        raise ValueError(
            f"Missing evaluation scores for {get_promo_id(promo)}: "
            f"{missing}"
        )

    weighted_score = sum(
        scores[criterion] * weight
        for criterion, weight in WEIGHTS.items()
    )

    return round(weighted_score, 3), scores, missing


def rank_promos(evaluation_data: dict) -> dict:
    """Rank all evaluated promos globally."""

    evaluated_promos = evaluation_data.get("evaluated_promos", [])

    if not isinstance(evaluated_promos, list):
        raise ValueError(
            "'evaluated_promos' must be a list in the evaluation JSON."
        )

    if not evaluated_promos:
        raise ValueError("No evaluated promos found in the input file.")

    ranked = []
    seen_ids = set()

    for item in evaluated_promos:

        if not isinstance(item, dict):
            continue

        promo_id = get_promo_id(item)

        if promo_id in seen_ids:
            print(f"Skipping duplicate promo: {promo_id}")
            continue

        seen_ids.add(promo_id)

        weighted_score, dimension_scores, missing = (
            calculate_weighted_score(item)
        )

        evaluation = item.get("evaluation", {})
        decision = get_decision(item)

        overall_score = evaluation.get("overall_score")

        segments = item.get("segments", [])
        formatted_segments = []
        for idx, s in enumerate(segments):
            formatted_segments.append({
                "segment_order": s.get("segment_order", idx + 1),
                "episode": s.get("episode", ""),
                "start_time": format_seconds(s.get("start_time")),
                "end_time": format_seconds(s.get("end_time")),
                "start_seconds": s.get("start_time"),
                "end_seconds": s.get("end_time"),
                "duration": s.get("duration"),
                "event_ids": s.get("event_ids", []),
            })

        hook = item.get("hook", {})
        cliffhanger = item.get("cliffhanger", {})
        warnings = item.get("validation_warnings", [])
        warning_codes = [
            w.get("code") if isinstance(w, dict) else str(w)
            for w in warnings
        ]

        ranked.append({
            "promo_id": promo_id,
            "weighted_score": weighted_score,
            "overall_score": overall_score,
            "decision": decision,
            "decision_priority": DECISION_ORDER[decision],
            "dimension_scores": dimension_scores,
            "missing_dimensions": missing,
            "pitch": evaluation.get("one_line_pitch", ""),
            "strengths": evaluation.get("strengths", []),
            "weaknesses": evaluation.get("weaknesses", []),
            "improvement_suggestion": evaluation.get(
                "improvement_suggestion", ""
            ),
            "construction_type": item.get("construction_type", "single_candidate"),
            "episodes": item.get("episodes", []),
            "total_duration": item.get("actual_duration") or item.get("total_duration"),
            "segments": formatted_segments,
            "raw_segments": segments,
            "hook": hook,
            "cliffhanger": cliffhanger,
            "warnings": warning_codes,
            "requires_manual_review": item.get("requires_manual_review", False),
            "evaluation": evaluation,
        })

    if not ranked:
        raise ValueError("No usable promo evaluations were found.")

    # Decision tier first, then weighted quality score.
    ranked.sort(
        key=lambda x: (
            x["decision_priority"],
            -x["weighted_score"],
            -(
                float(x["overall_score"])
                if isinstance(x["overall_score"], (int, float))
                else 0.0
            ),
            x["promo_id"],
        )
    )

    for position, promo in enumerate(ranked, start=1):
        promo["global_rank"] = position
        promo.pop("decision_priority", None)

    recommended = [
        p for p in ranked if p["decision"] == "recommend"
    ]

    needing_revision = [
        p for p in ranked if p["decision"] == "revise"
    ]

    rejected = [
        p for p in ranked if p["decision"] == "reject"
    ]

    return {
        "ranking_method": {
            "description": (
                "Global ranking by evaluator decision tier, "
                "then weighted quality score."
            ),
            "weights": WEIGHTS,
            "score_range": "0-10",
        },
        "statistics": {
            "total_ranked": len(ranked),
            "recommended": len(recommended),
            "needing_revision": len(needing_revision),
            "rejected": len(rejected),
        },
        "ranked_promos": ranked,
        "recommended_promos": recommended,
        "promos_needing_revision": needing_revision,
        "rejected_promos": rejected,
    }


def save_outputs(results: dict, output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    """Save ranked_promos.json/csv and final_promos.json/csv."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_ranked = out_dir / "ranked_promos.json"
    csv_ranked = out_dir / "ranked_promos.csv"
    json_final = out_dir / "final_promos.json"
    csv_final = out_dir / "final_promos.csv"

    # 1. Save ranked_promos.json
    with json_ranked.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)

    # 2. Save ranked_promos.csv
    fields = [
        "global_rank",
        "promo_id",
        "weighted_score",
        "overall_score",
        "decision",
        "opening_hook",
        "standalone_coherence",
        "narrative_flow",
        "emotional_impact",
        "cliffhanger_effectiveness",
        "promotional_appeal",
        "pitch",
    ]

    with csv_ranked.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for promo in results["ranked_promos"]:
            row = {
                "global_rank": promo["global_rank"],
                "promo_id": promo["promo_id"],
                "weighted_score": promo["weighted_score"],
                "overall_score": promo["overall_score"],
                "decision": promo["decision"],
                "pitch": promo["pitch"],
            }
            row.update(promo["dimension_scores"])
            writer.writerow(row)

    # 3. Save final_promos.json (standardized assignment output)
    final_list = []
    for promo in results["ranked_promos"]:
        final_list.append({
            "rank": promo["global_rank"],
            "promo_id": promo["promo_id"],
            "episodes": promo.get("episodes", []),
            "total_duration": promo.get("total_duration"),
            "segments": promo.get("segments", []),
            "hook": promo.get("hook", {}),
            "cliffhanger": promo.get("cliffhanger", {}),
            "one_line_pitch": promo.get("pitch", ""),
            "overall_score": promo.get("overall_score") or promo.get("weighted_score"),
            "weighted_score": promo.get("weighted_score"),
            "decision": promo.get("decision"),
            "dimension_scores": promo.get("dimension_scores", {}),
            "ranking_reason": "; ".join(promo.get("strengths", [])),
            "strengths": promo.get("strengths", []),
            "weaknesses": promo.get("weaknesses", []),
            "improvement_suggestion": promo.get("improvement_suggestion", ""),
            "warnings": promo.get("warnings", []),
        })

    with json_final.open("w", encoding="utf-8") as file:
        json.dump(final_list, file, indent=2, ensure_ascii=False)

    # 4. Save final_promos.csv
    final_fields = [
        "rank",
        "promo_id",
        "episodes",
        "total_duration",
        "segment_count",
        "segments",
        "hook_summary",
        "cliffhanger_summary",
        "one_line_pitch",
        "overall_score",
        "decision",
        "ranking_reason",
        "warnings",
    ]

    with csv_final.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=final_fields)
        writer.writeheader()

        for item in final_list:
            segs_summary = "; ".join(
                f"[{s.get('episode')}] {s.get('start_time')}-{s.get('end_time')} ({s.get('duration')}s)"
                for s in item.get("segments", [])
            )
            hk = item.get("hook", {})
            hook_summary = hk.get("evidence_text") or hk.get("type", "")
            cl = item.get("cliffhanger", {})
            cliff_summary = cl.get("evidence_text") or cl.get("type", "")

            writer.writerow({
                "rank": item["rank"],
                "promo_id": item["promo_id"],
                "episodes": ", ".join(str(ep) for ep in item.get("episodes", [])),
                "total_duration": item.get("total_duration"),
                "segment_count": len(item.get("segments", [])),
                "segments": segs_summary,
                "hook_summary": hook_summary,
                "cliffhanger_summary": cliff_summary,
                "one_line_pitch": item.get("one_line_pitch", ""),
                "overall_score": item.get("overall_score"),
                "decision": item.get("decision"),
                "ranking_reason": item.get("ranking_reason", ""),
                "warnings": "; ".join(item.get("warnings", [])),
            })

    return {
        "ranked_json": json_ranked,
        "ranked_csv": csv_ranked,
        "final_json": json_final,
        "final_csv": csv_final,
    }


def rank_and_export(
    input_path: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> dict:
    """Rank evaluated promos and write ranked_promos.* and final_promos.*."""
    in_path = Path(input_path) if input_path else DEFAULT_INPUT_PATH
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    evaluation_data = load_json(in_path)
    results = rank_promos(evaluation_data)
    saved_paths = save_outputs(results, out_dir)
    results["saved_paths"] = saved_paths
    return results


def main(input_path=None, output_dir=None) -> None:
    print("\n========== GLOBAL PROMO RANKER ==========")

    results = rank_and_export(input_path=input_path, output_dir=output_dir)
    stats = results["statistics"]
    saved_paths = results.get("saved_paths", {})

    print("\n========== RANKING SUMMARY ==========")
    print(f"Total promos ranked: {stats['total_ranked']}")
    print(f"Recommended: {stats['recommended']}")
    print(f"Need revision: {stats['needing_revision']}")
    print(f"Rejected: {stats['rejected']}")

    print("\n========== TOP 10 PROMOS ==========")

    for promo in results["ranked_promos"][:10]:
        print(
            f"#{promo['global_rank']} "
            f"{promo['promo_id']} | "
            f"Score: {promo['weighted_score']}/10 | "
            f"Decision: {promo['decision']}"
        )

    print("\nFiles saved:")
    for name, p in saved_paths.items():
        print(f"{name}: {p}")

    print("\nRanking completed successfully.")


if __name__ == "__main__":
    main()
