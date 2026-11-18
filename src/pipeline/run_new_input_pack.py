"""Run the reusable promo pipeline on a new ZIP/TXT screenplay pack.

The script reuses the Layer 1/Layer 2 provider router. It never invokes
Semantic Verifier V4; new packs produce within-episode compositions only
unless a separately reviewed verified-pair file is supplied in future.
"""

import argparse
import json
import re
from pathlib import Path

from src.parser.script_parser import main as parse_screenplays
from src.llm.layer1_event_identification import run_layer1
from src.candidate_generation.candidate_generator import run_candidate_generation
from src.llm.layer2_candidate_evaluation import run_layer2_evaluation
from src.promo_composer.candidate_loader import build_screenplay_event_pool
from src.promo_composer.segment_selector import select_promo_segments
from src.promo_composer.promo_builder import build_promos
from src.promo_composer.promo_validator import validate_promos


ROOT = Path(__file__).resolve().parents[2]


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(input_path, output_dir, evaluate=False):
    output_dir = Path(output_dir).resolve()
    parsed_path = output_dir / "parsed_episodes.json"
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    parse_screenplays(input_path, parsed_path)
    parsed = read_json(parsed_path)
    episodes = parsed.get("episodes", [])
    failures = []

    for episode in episodes:
        match = re.search(r"\d+", str(episode.get("episode", "")))
        if not match:
            failures.append({"episode": episode.get("episode"), "error": "No numeric episode identifier."})
            continue
        number = int(match.group())
        try:
            run_layer1(number, parsed_path, reports_dir, raw_dir)
            run_candidate_generation(number, parsed_path, raw_dir)
            candidate_path = raw_dir / f"candidates_episode{number}.json"
            candidates = read_json(candidate_path).get("candidates", [])
            if candidates:
                run_layer2_evaluation(number, raw_dir)
            else:
                write_json({"episode": f"EP{number:03d}", "evaluated_candidates": [], "ranking": []},
                           raw_dir / f"layer2_episode{number}_evaluation.json")
        except Exception as exc:
            failures.append({"episode": f"EP{number:03d}", "error": str(exc)})

    screenplay_events = build_screenplay_event_pool(parsed)
    evaluated_candidates = []
    for episode in episodes:
        match = re.search(r"\d+", str(episode.get("episode", "")))
        if not match:
            continue
        number = int(match.group())
        candidate_path = raw_dir / f"candidates_episode{number}.json"
        evaluation_path = raw_dir / f"layer2_episode{number}_evaluation.json"
        if not candidate_path.exists() or not evaluation_path.exists():
            continue
        candidate_data = read_json(candidate_path)
        evaluation_data = read_json(evaluation_path)
        evaluations = {
            item.get("candidate_id"): item
            for item in evaluation_data.get("evaluated_candidates", [])
        }
        evaluated_candidates.extend(
            {**candidate, "evaluation": evaluations[candidate["candidate_id"]]}
            for candidate in candidate_data.get("candidates", [])
            if candidate.get("candidate_id") in evaluations
        )

    selection = select_promo_segments({
        "screenplay_events": screenplay_events,
        "evaluated_candidates": evaluated_candidates,
    }, verified_pairs=[])
    builder = build_promos(selection)
    validation = validate_promos(builder)
    write_json(selection, raw_dir / "promo_segment_selection.json")
    write_json(builder, raw_dir / "promo_builder_results.json")
    write_json(validation, raw_dir / "promo_validation_results.json")
    write_json({"failed_episodes": failures}, output_dir / "run_failures.json")

    if evaluate and validation.get("valid_promos"):
        from src.promo_composer.promo_evaluator import evaluate_promos
        results = evaluate_promos(validation)
        write_json(results, raw_dir / "promo_evaluation.json")

    return {
        "episodes_in_pack": len(episodes),
        "episodes_failed": len(failures),
        "candidates_evaluated": len(evaluated_candidates),
        "promos_built": len(builder.get("promos", [])),
        "valid_promos": len(validation.get("valid_promos", [])),
        "failures": failures,
        "output_dir": str(output_dir),
        "llm_promo_evaluation_requested": evaluate,
        "semantic_verifier_v4_called": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a new screenplay input pack.")
    parser.add_argument("--input", required=True, help="ZIP, TXT file, or directory of TXT screenplays.")
    parser.add_argument("--output-dir", required=True, help="New output directory; the source input is never modified.")
    parser.add_argument("--evaluate", action="store_true", help="Run promo-level LLM evaluation after structural validation (uses configured provider/API).")
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output_dir, evaluate=args.evaluate), indent=2))
