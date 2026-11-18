"""Build final quality reports from frozen validation, evaluation, and ledger outputs."""

import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "outputs" / "raw"
REPORTS = ROOT / "outputs" / "reports"
SUBMISSION = ROOT / "submission"


def read_json(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main():
    validation = read_json(RAW / "expanded" / "promo_validation_results.json")
    evaluation = read_json(RAW / "expanded" / "promo_evaluation.json")
    selection = read_json(RAW / "expanded" / "promo_segment_selection.json")
    ledger_path = REPORTS / "editorial_review_ledger.csv"
    with ledger_path.open("r", encoding="utf-8-sig", newline="") as stream:
        ledger = list(csv.DictReader(stream))

    validated = validation.get("validated_promos", [])
    evaluated = evaluation.get("evaluated_promos", [])
    if len(validated) != 134 or len(evaluated) != 134 or len(ledger) != 134:
        raise ValueError("Expected 134 validation, evaluation, and ledger rows.")
    validated_ids = {item["promo_id"] for item in validated}
    evaluated_ids = {item["promo_id"] for item in evaluated}
    ledger_ids = {item["promo_id"] for item in ledger}
    if validated_ids != evaluated_ids or validated_ids != ledger_ids:
        raise ValueError("Validation, evaluation, and editorial ledger IDs do not match.")

    warning_counts = Counter()
    warning_samples = defaultdict(list)
    for promo in validated:
        for warning in promo.get("validation_warnings", []):
            code = warning.get("code", "UNKNOWN")
            warning_counts[code] += 1
            if len(warning_samples[code]) < 8:
                warning_samples[code].append(promo["promo_id"])

    stats = evaluation["statistics"]
    validation_stats = validation["statistics"]
    decisions = Counter(item["evaluation"]["decision"] for item in evaluated)
    dimensions = [
        "opening_hook", "standalone_coherence", "narrative_flow",
        "emotional_impact", "cliffhanger_effectiveness", "promotional_appeal",
    ]
    means = {
        name: round(sum(item["evaluation"][name] for item in evaluated) / len(evaluated), 2)
        for name in dimensions
    }
    ranked = sorted(evaluated, key=lambda item: item["evaluation"]["overall_score"], reverse=True)
    missing_hook_ids = {row["promo_id"] for row in ledger if row["hook_warning"] == "Yes"}
    missing_cliff_ids = {row["promo_id"] for row in ledger if row["cliffhanger_warning"] == "Yes"}
    high_risk_hook = [item for item in evaluated if item["promo_id"] in missing_hook_ids and item["evaluation"]["decision"] == "recommend"]
    high_risk_cliff = [item for item in evaluated if item["promo_id"] in missing_cliff_ids and item["evaluation"]["decision"] == "recommend"]
    human_status = Counter(row["editorial_decision"] for row in ledger)
    new_compositions = selection.get("same_episode_combinations", []) + selection.get("verified_hub_montages", [])
    report = {
        "generated_from": {
            "expanded_validation": "outputs/raw/expanded/promo_validation_results.json",
            "expanded_evaluation": "outputs/raw/expanded/promo_evaluation.json",
            "expanded_selection": "outputs/raw/expanded/promo_segment_selection.json",
            "editorial_review_ledger": "outputs/reports/editorial_review_ledger.csv",
            "semantic_verifier_v4_rerun": False,
            "promo_evaluator_rerun_during_report_generation": False,
        },
        "automated_results": {
            "evaluation_prompt_sha256": stats.get("prompt_sha256"),
            "provider": stats.get("provider"),
            "model": stats.get("model"),
            "evaluated_promos": stats.get("total_evaluated"),
            "newly_evaluated": stats.get("newly_evaluated"),
            "reused_existing_evaluations": stats.get("reused_existing_evaluations"),
            "decisions": dict(decisions),
            "mean_dimension_scores": means,
            "mean_overall_score": round(sum(item["evaluation"]["overall_score"] for item in evaluated) / len(evaluated), 2),
            "top_promos": [
                {"rank": rank, "promo_id": item["promo_id"], "score": item["evaluation"]["overall_score"], "decision": item["evaluation"]["decision"], "pitch": item["evaluation"].get("one_line_pitch", "")}
                for rank, item in enumerate(ranked[:10], start=1)
            ],
            "structural_validation": validation_stats,
            "warning_counts_by_code": dict(warning_counts.most_common()),
            "warning_sample_promo_ids": dict(warning_samples),
            "expanded_composition": {
                "frozen_v4_cross_episode_combinations": len(selection.get("cross_episode_combinations", [])),
                "same_episode_montage_candidates": len(selection.get("same_episode_combinations", [])),
                "verified_hub_montage_candidates": len(selection.get("verified_hub_montages", [])),
                "new_compositions": len(new_compositions),
            },
            "recommended_with_missing_hook_evidence": sorted(item["promo_id"] for item in high_risk_hook),
            "recommended_with_missing_cliffhanger_evidence": sorted(item["promo_id"] for item in high_risk_cliff),
        },
        "human_editorial_review": {
            "status": "deferred for prototype; not performed",
            "ledger_rows": len(ledger),
            "editorial_decisions": dict(human_status),
            "hook_review_pending": len(ledger),
            "cliffhanger_review_pending": len(ledger),
            "standalone_coherence_review_pending": len(ledger),
            "narrative_continuity_review_pending": sum(row["narrative_continuity"] == "Pending review" for row in ledger),
            "new_composition_review_pending": len(new_compositions),
            "note": "Automated evidence flags and evaluator decisions are not human approval.",
        },
        "limitations": [
            "The evaluator score is an automated assessment and is not editorial approval.",
            "Structural evidence checks cannot determine whether a hook is attention-grabbing or an ending is truly unresolved.",
            "Standalone coherence and narrative continuity have not received human review.",
            "The three-part hub montage has frozen V4 evidence from its hub to each spoke, but no direct V4 evidence between the two spokes.",
            "Screenplay text cannot verify what appears in the final footage.",
        ],
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    md = [
        "# AI Promo Finder - Quality and Failure Analysis", "",
        "Generated from frozen local outputs. Report generation made no model calls; Semantic Verifier V4 and the promo evaluator were not rerun.", "",
        "## Automated results", "",
        f"- Evaluator: {stats.get('provider')} / {stats.get('model')}; prompt SHA-256 `{stats.get('prompt_sha256')}`.",
        f"- Evaluated: {stats.get('total_evaluated')} promos ({stats.get('newly_evaluated')} new evaluations; {stats.get('reused_existing_evaluations')} reused).",
        f"- Decisions: {dict(decisions)}.",
        f"- Mean overall evaluator score: {report['automated_results']['mean_overall_score']:.2f} / 10.",
        f"- Structural validation: {validation_stats.get('valid_promos')} / {validation_stats.get('total_promos_received')} valid; {validation_stats.get('total_hard_errors')} hard errors; {validation_stats.get('total_quality_warnings')} warnings.",
        f"- Duration range: {validation_stats.get('duration_min')}-{validation_stats.get('duration_max')} seconds.",
        f"- New compositions: {len(new_compositions)} (28 same-episode and 1 verified-hub candidate); all included in the 134-promo evaluator run.",
        "", "### Evaluator mean scores", "", "| Dimension | Mean / 10 |", "|---|---:|",
    ]
    for dimension, score in means.items():
        md.append(f"| {dimension.replace('_', ' ').title()} | {score:.2f} |")
    md += ["", "### Structural warning counts", "", "| Warning | Count | Example promos |", "|---|---:|---|"]
    for code, count in warning_counts.most_common():
        md.append(f"| `{code}` | {count} | {', '.join(warning_samples[code])} |")
    md += [
        "", "## Human editorial results", "",
        "**Human review was deferred for this prototype and has not been performed.** The ledger contains 134 rows; every editorial decision, hook check, cliffhanger check, and standalone-coherence check remains pending. Narrative continuity is pending for multi-segment promos. The 29 new compositions still require editorial review.", "",
        f"- Recommended promos with missing hook evidence: {len(high_risk_hook)} ({', '.join(sorted(item['promo_id'] for item in high_risk_hook))}).",
        f"- Recommended promos with missing cliffhanger evidence: {len(high_risk_cliff)} ({', '.join(sorted(item['promo_id'] for item in high_risk_cliff))}).",
        "- Automated evaluator decisions and scores do not constitute human approval.",
        "", "## Unresolved warnings and limitations", "",
    ]
    md += [f"- {item}" for item in report["limitations"]]
    md += ["", "## Source files", "", "- Frozen evaluation: `outputs/raw/expanded/promo_evaluation.json`.", "- Frozen validation: `outputs/raw/expanded/promo_validation_results.json`.", "- Human review ledger: `outputs/reports/editorial_review_ledger.csv`.", ""]
    markdown_text = "\n".join(md)

    # Keep the existing promo_quality_report names and provide the requested quality_report names.
    for stem in ("quality_report", "promo_quality_report"):
        (REPORTS / f"{stem}.json").write_text(json_text, encoding="utf-8")
        (REPORTS / f"{stem}.md").write_text(markdown_text, encoding="utf-8")
    SUBMISSION.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPORTS / "quality_report.json", SUBMISSION / "quality_report.json")
    shutil.copyfile(REPORTS / "quality_report.md", SUBMISSION / "quality_report.md")
    print(f"Saved report JSON and Markdown in {REPORTS}")
    print(f"Saved submission copies in {SUBMISSION}")


if __name__ == "__main__":
    main()
