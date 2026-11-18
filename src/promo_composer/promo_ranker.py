
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

INPUT_PATH = PROJECT_ROOT / "outputs" / "raw" / "promo_evaluation.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "final"

OUTPUT_JSON = OUTPUT_DIR / "ranked_promos.json"
OUTPUT_CSV = OUTPUT_DIR / "ranked_promos.csv"

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


def save_json(results: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_JSON.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)


def save_csv(results: dict) -> None:
    """Save a compact, spreadsheet-friendly ranking."""

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

    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

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


def main() -> None:
    print("\n========== GLOBAL PROMO RANKER ==========")

    evaluation_data = load_json(INPUT_PATH)

    results = rank_promos(evaluation_data)

    save_json(results)
    save_csv(results)

    stats = results["statistics"]

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
    print(f"JSON: {OUTPUT_JSON}")
    print(f"CSV:  {OUTPUT_CSV}")

    print("\nRanking completed successfully.")


if __name__ == "__main__":
    main()
