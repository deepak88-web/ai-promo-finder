
import json
import argparse
from pathlib import Path

from src.promo_composer.candidate_loader import (
    load_promo_composer_data,
)
from src.promo_composer.segment_selector import (
    select_promo_segments,
)
from src.promo_composer.promo_builder import (
    build_promos,
)
from src.promo_composer.promo_validator import (
    validate_promos,
    print_validation_summary,
)


# Project root
ROOT = Path(__file__).resolve().parents[2]

# Existing, frozen Semantic Verifier V4 output
V4_PATH = (
    ROOT
    / "outputs"
    / "interim"
    / "semantic_verification_refined_v4.json"
)

# Output files
OUTPUT_DIR = ROOT / "outputs" / "raw"
EXPANDED_OUTPUT_DIR = OUTPUT_DIR / "expanded"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_verified_pairs():
    """Load the existing V4 semantic verification results."""

    if not V4_PATH.exists():
        raise FileNotFoundError(
            f"Semantic Verifier V4 output not found: {V4_PATH}"
        )

    with open(V4_PATH, "r", encoding="utf-8") as file:
        verified_pairs = json.load(file)

    if not isinstance(verified_pairs, list):
        raise ValueError(
            "V4 output must contain a list of verified pairs."
        )

    return verified_pairs


def save_json(data, filename, output_dir=OUTPUT_DIR):
    """Save pipeline output as formatted JSON."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    print(f"Saved: {path}")


def main(expanded=False):

    output_dir = EXPANDED_OUTPUT_DIR if expanded else OUTPUT_DIR

    print("\n========== AI PROMO FINDER PIPELINE ==========")

    # 1. Load screenplay events and Layer 2 candidates
    print("\n[1/5] Loading project data...")

    data = load_promo_composer_data()

    # 2. Load existing V4 verification results
    print("\n[2/5] Loading Semantic Verifier V4 results...")

    verified_pairs = load_verified_pairs()

    print(f"Verified pairs loaded: {len(verified_pairs)}")

    # 3. Select individual segments and cross-episode combinations
    print("\n[3/5] Selecting promo segments...")

    selection_results = select_promo_segments(
        data,
        verified_pairs=verified_pairs,
    )

    save_json(
        selection_results,
        "promo_segment_selection.json",
        output_dir,
    )

    # 4. Build complete promo candidates
    print("\n[4/5] Building promo candidates...")

    builder_results = build_promos(selection_results)

    save_json(
        builder_results,
        "promo_builder_results.json",
        output_dir,
    )

    # 5. Validate all constructed promos
    print("\n[5/5] Validating promo candidates...")

    validation_results = validate_promos(builder_results)

    save_json(
        validation_results,
        "promo_validation_results.json",
        output_dir,
    )

    print_validation_summary(validation_results)

    # Final summary
    print("\n========== PIPELINE SUMMARY ==========")

    print(
        "Individual segments selected:",
        selection_results["statistics"][
            "selected_candidate_segments"
        ],
    )

    print(
        "Cross-episode combinations selected:",
        selection_results["statistics"][
            "selected_cross_episode_combinations"
        ],
    )

    print(
        "Promos constructed:",
        len(builder_results.get("promos", [])),
    )

    print(
        "Valid promos:",
        len(validation_results["valid_promos"]),
    )

    print(
        "Invalid promos:",
        len(validation_results["invalid_promos"]),
    )

    print("\nPipeline execution completed.")
    print("======================================")
    if expanded:
        print("Expanded draft outputs saved separately; frozen V4 input was loaded unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compose and validate promos from saved inputs.")
    parser.add_argument(
        "--expanded",
        action="store_true",
        help="Save expanded same-episode and verified-hub candidates under outputs/raw/expanded without overwriting baseline outputs.",
    )
    args = parser.parse_args()
    main(expanded=args.expanded)
