"""Create a one-row-per-promo human review ledger from saved outputs."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_PATH = ROOT / "outputs" / "raw" / "expanded" / "promo_validation_results.json"
EVALUATION_PATH = ROOT / "outputs" / "raw" / "expanded" / "promo_evaluation.json"
OUTPUT_PATH = ROOT / "outputs" / "reports" / "editorial_review_ledger.csv"


def read_json(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def priority_for(promo, evaluation, warning_codes):
    decision = (evaluation or {}).get("decision", "unknown")
    missing_hook = "HOOK_NOT_IDENTIFIED" in warning_codes
    missing_cliff = "CLIFFHANGER_NOT_IDENTIFIED" in warning_codes
    is_new = promo.get("promo_id", "").startswith(("PROMO_SAME_", "PROMO_SAME3_", "PROMO_HUB_"))

    if decision == "recommend" and (missing_hook or missing_cliff):
        reasons = []
        if missing_hook:
            reasons.append("missing hook evidence")
        if missing_cliff:
            reasons.append("missing cliffhanger evidence")
        return "P1 - High-risk recommendation", "Recommended despite " + " and ".join(reasons)
    if is_new:
        return "P2 - New composition", "New composition requires human transition and coherence review"
    return "P3 - Standard review", "Review evaluator assessment and any source-evidence warnings"


def build_rows(validation, evaluation):
    validated = validation.get("validated_promos", [])
    evaluated = evaluation.get("evaluated_promos", [])
    validation_by_id = {item.get("promo_id"): item for item in validated}
    evaluation_by_id = {item.get("promo_id"): item for item in evaluated}

    if len(validation_by_id) != len(validated):
        raise ValueError("Validation data contains duplicate promo IDs.")
    if len(evaluation_by_id) != len(evaluated):
        raise ValueError("Evaluation data contains duplicate promo IDs.")
    if set(validation_by_id) != set(evaluation_by_id):
        missing_eval = sorted(set(validation_by_id) - set(evaluation_by_id))
        missing_validation = sorted(set(evaluation_by_id) - set(validation_by_id))
        raise ValueError(
            f"Promo IDs do not reconcile. Missing evaluations={missing_eval}; "
            f"missing validations={missing_validation}"
        )

    rows = []
    for promo_id, promo in validation_by_id.items():
        evaluation_item = evaluation_by_id[promo_id]
        model_evaluation = evaluation_item.get("evaluation") or {}
        warnings = promo.get("validation_warnings", [])
        warning_codes = sorted({item.get("code", "UNKNOWN") for item in warnings})
        has_hook_gap = "HOOK_NOT_IDENTIFIED" in warning_codes
        has_cliff_gap = "CLIFFHANGER_NOT_IDENTIFIED" in warning_codes
        priority, rationale = priority_for(promo, model_evaluation, warning_codes)
        segments = promo.get("segments", [])
        episode_list = promo.get("episodes", [])

        rows.append({
            "review_priority": priority,
            "priority_rationale": rationale,
            "promo_id": promo_id,
            "evaluator_decision": model_evaluation.get("decision", "unknown").title(),
            "evaluator_score": model_evaluation.get("overall_score", ""),
            "construction_type": promo.get("construction_type", ""),
            "is_new_composition": "Yes" if promo_id.startswith(("PROMO_SAME_", "PROMO_SAME3_", "PROMO_HUB_")) else "No",
            "episodes": ";".join(str(item) for item in episode_list),
            "segment_count": len(segments),
            "duration_seconds": promo.get("actual_duration", promo.get("total_duration", "")),
            "hook_evidence": "Pending review",
            "hook_warning": "Yes" if has_hook_gap else "No",
            "cliffhanger_evidence": "Pending review",
            "cliffhanger_warning": "Yes" if has_cliff_gap else "No",
            "standalone_coherence": "Pending review",
            "narrative_continuity": "N/A" if len(segments) == 1 else "Pending review",
            "editorial_decision": "Pending",
            "reviewer_notes": "",
            "validation_warning_codes": ";".join(warning_codes),
        })

    priority_order = {
        "P1 - High-risk recommendation": 0,
        "P2 - New composition": 1,
        "P3 - Standard review": 2,
    }
    rows.sort(key=lambda item: (
        priority_order[item["review_priority"]],
        -float(item["evaluator_score"] or 0),
        item["promo_id"],
    ))
    return rows


def main():
    if not VALIDATION_PATH.exists() or not EVALUATION_PATH.exists():
        raise FileNotFoundError("Expanded validation and evaluation outputs are required.")
    validation = read_json(VALIDATION_PATH)
    evaluation = read_json(EVALUATION_PATH)
    rows = build_rows(validation, evaluation)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0]) if rows else []
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    priorities = {}
    for row in rows:
        priorities[row["review_priority"]] = priorities.get(row["review_priority"], 0) + 1
    print(f"Created {OUTPUT_PATH}")
    print(f"Ledger rows: {len(rows)}")
    print(f"Priority counts: {priorities}")
    print("All human-review fields start as pending; no human decision was inferred.")


if __name__ == "__main__":
    main()
