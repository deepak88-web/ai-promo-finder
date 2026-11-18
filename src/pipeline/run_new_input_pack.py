"""Run the reusable promo pipeline on a new ZIP/TXT screenplay pack.

The script reuses the Layer 1/Layer 2 provider router. It never invokes
Semantic Verifier V4; new packs produce within-episode compositions only
unless a separately reviewed verified-pair file is supplied in future.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.parser.script_parser import main as parse_screenplays
from src.llm.layer1_event_identification import run_layer1
from src.candidate_generation.candidate_generator import run_candidate_generation
from src.llm.layer2_candidate_evaluation import run_layer2_evaluation
from src.promo_composer.candidate_loader import build_screenplay_event_pool
from src.promo_composer.segment_selector import select_promo_segments
from src.promo_composer.promo_builder import build_promos
from src.promo_composer.promo_validator import validate_promos
from src.pipeline.consolidate_results import consolidate_results
from src.promo_composer.promo_ranker import rank_and_export


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(
    input_path,
    output_dir,
    evaluate=False,
    provider=None,
    model=None,
    api_key=None,
    base_url=None,
    cross_episode=False,
    layer1_provider=None,
    layer1_model=None,
    layer1_key=None,
    layer2_provider=None,
    layer2_model=None,
    layer2_key=None,
    promo_eval_provider=None,
    promo_eval_model=None,
    promo_eval_key=None,
):
    output_dir = Path(output_dir).resolve()
    parsed_path = output_dir / "parsed_episodes.json"
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    final_dir = output_dir / "final"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    # Resolve per-layer configurations with unified fallback
    l1_provider = layer1_provider or provider
    l1_model = layer1_model or model
    l1_key = layer1_key or api_key

    l2_provider = layer2_provider or provider
    l2_model = layer2_model or model
    l2_key = layer2_key or api_key

    pe_provider = promo_eval_provider or provider
    pe_model = promo_eval_model or model
    pe_key = promo_eval_key or api_key

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
            run_layer1(
                number,
                parsed_path=parsed_path,
                reports_dir=reports_dir,
                raw_dir=raw_dir,
                provider=l1_provider,
                model=l1_model,
                api_key=l1_key,
                base_url=base_url,
            )
            run_candidate_generation(number, parsed_path, raw_dir)
            candidate_path = raw_dir / f"candidates_episode{number}.json"
            candidates = read_json(candidate_path).get("candidates", [])
            if candidates:
                run_layer2_evaluation(
                    number,
                    raw_dir=raw_dir,
                    provider=l2_provider,
                    model=l2_model,
                    api_key=l2_key,
                    base_url=base_url,
                )
            else:
                write_json(
                    {"episode": f"EP{number:03d}", "evaluated_candidates": [], "ranking": []},
                    raw_dir / f"layer2_episode{number}_evaluation.json",
                )
        except Exception as exc:
            failures.append({"episode": f"EP{number:03d}", "error": str(exc)})

    # Consolidate candidate evaluations across episodes
    consolidate_results(raw_dir=raw_dir, report_dir=reports_dir)

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

    final_results = None
    if evaluate and validation.get("valid_promos"):
        from src.promo_composer.promo_evaluator import evaluate_promos
        eval_results = evaluate_promos(
            validation,
            provider=pe_provider,
            model=pe_model,
            api_key=pe_key,
            base_url=base_url,
            reuse_cache=False,
        )
        eval_path = raw_dir / "promo_evaluation.json"
        write_json(eval_results, eval_path)

        # Produce unified rankings & final promos
        final_results = rank_and_export(input_path=eval_path, output_dir=final_dir)

    return {
        "episodes_in_pack": len(episodes),
        "episodes_failed": len(failures),
        "candidates_evaluated": len(evaluated_candidates),
        "promos_built": len(builder.get("promos", [])),
        "valid_promos": len(validation.get("valid_promos", [])),
        "failures": failures,
        "output_dir": str(output_dir),
        "llm_promo_evaluation_requested": evaluate,
        "final_promos_ranked": len(final_results["ranked_promos"]) if final_results else 0,
        "semantic_verifier_v4_called": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a new screenplay input pack.")
    parser.add_argument("--input", required=True, help="ZIP, TXT file, or directory of TXT screenplays.")
    parser.add_argument("--output-dir", required=True, help="New output directory; the source input is never modified.")
    parser.add_argument("--evaluate", action="store_true", help="Run promo-level LLM evaluation after structural validation.")
    parser.add_argument("--provider", default=None, help="LLM provider (gemini, groq, openai_compatible, mock).")
    parser.add_argument("--model", default=None, help="Model name.")
    parser.add_argument("--api-key", default=None, help="API key override (never saved to disk).")
    parser.add_argument("--base-url", default=None, help="Base URL for OpenAI-compatible endpoint.")
    parser.add_argument("--cross-episode", action="store_true", help="Allow cross-episode promo combinations.")
    parser.add_argument("--layer1-provider", default=None, help="Provider override for Layer 1.")
    parser.add_argument("--layer1-model", default=None, help="Model override for Layer 1.")
    parser.add_argument("--layer2-provider", default=None, help="Provider override for Layer 2.")
    parser.add_argument("--layer2-model", default=None, help="Model override for Layer 2.")
    parser.add_argument("--promo-eval-provider", default=None, help="Provider override for Promo Evaluation.")
    parser.add_argument("--promo-eval-model", default=None, help="Model override for Promo Evaluation.")
    args = parser.parse_args()
    print(json.dumps(run(
        args.input,
        args.output_dir,
        evaluate=args.evaluate,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        cross_episode=args.cross_episode,
        layer1_provider=args.layer1_provider,
        layer1_model=args.layer1_model,
        layer2_provider=args.layer2_provider,
        layer2_model=args.layer2_model,
        promo_eval_provider=args.promo_eval_provider,
        promo_eval_model=args.promo_eval_model,
    ), indent=2))
