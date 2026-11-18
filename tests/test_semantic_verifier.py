from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from src.promo_composer.candidate_loader import load_promo_composer_data
from src.promo_composer.compatibility_analyzer import (
    run_compatibility_analysis,
    build_event_profiles,
    clean_profile_keywords,
)
from src.promo_composer.semantic_verifier import (
    verify_candidate_pairs,
    save_verification_results,
)


OUTPUT_PATH = "outputs/interim/semantic_verification_refined_v4.json"
TEST_PAIR_LIMIT = 10

VALID_CONNECTION_MODES = {
    "narrative_connection",
    "thematic_connection",
    "emotional_visual_juxtaposition",
    "repetition",
    "none",
}


print("Loading screenplay data...")
data = load_promo_composer_data()

print("Building event profiles...")
profiles = build_event_profiles(data)
clean_profile_keywords(profiles)

print("Running compatibility analysis...")
results = run_compatibility_analysis(data)
pairs = results["cross_episode_pairs"]
test_pairs = pairs[:TEST_PAIR_LIMIT]

print(f"Selected pairs: {len(test_pairs)}")


print("Starting Gemini semantic verification V4...")

verified_pairs = verify_candidate_pairs(
    pairs=test_pairs,
    profiles=profiles,
    batch_size=5,
    context_window=2,
)


# ============================================================
# DETERMINISTIC REGRESSION CHECKS
# ============================================================

assert len(verified_pairs) == len(test_pairs), (
    f"Expected {len(test_pairs)} results, got {len(verified_pairs)}."
)

for pair in verified_pairs:

    evaluation = pair["semantic_verification"]
    pair_id = evaluation["pair_id"]

    required_fields = [
        "classification",
        "semantic_score",
        "relationship_type",
        "connection_mode",
        "best_sequence",
        "evidence_a",
        "evidence_b",
        "chronological_order",
        "connection_explanation",
        "sequence_explanation",
        "requires_manual_review",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in evaluation
    ]

    assert not missing_fields, (
        f"{pair_id} is missing fields: {missing_fields}"
    )

    assert evaluation["connection_mode"] in VALID_CONNECTION_MODES, (
        f"{pair_id} has invalid connection_mode."
    )

    # Weak and rejected pairs must not recommend a promotional order.
    if evaluation["classification"] in {"weak", "reject"}:

        assert evaluation["best_sequence"] == "NEITHER", (
            f"{pair_id}: weak/reject pair must use NEITHER sequence."
        )

    # Repetitive or unrelated pairs must not recommend a promotional order.
    if evaluation["connection_mode"] in {"repetition", "none"}:

        assert evaluation["best_sequence"] == "NEITHER", (
            f"{pair_id}: repetition/none connection must use NEITHER."
        )

    # UNCLEAR chronology must not retain chronology evidence.
    if evaluation["chronological_order"] == "UNCLEAR":

        assert not evaluation.get("chronology_evidence_a"), (
            f"{pair_id}: UNCLEAR chronology should not retain evidence A."
        )

        assert not evaluation.get("chronology_evidence_b"), (
            f"{pair_id}: UNCLEAR chronology should not retain evidence B."
        )


# Save only after all deterministic checks pass.
save_verification_results(
    verified_pairs,
    OUTPUT_PATH
)


# ============================================================
# SUMMARY
# ============================================================

counts = Counter(
    pair["semantic_verification"]["classification"]
    for pair in verified_pairs
)

manual_review_count = sum(
    pair["semantic_verification"]["requires_manual_review"]
    for pair in verified_pairs
)


# ============================================================
# DISPLAY RESULTS
# ============================================================

print("\n========== SEMANTIC VERIFICATION V4 ==========")

for pair in verified_pairs:

    evaluation = pair["semantic_verification"]

    print(f"\n{evaluation['pair_id']}: {evaluation['classification']}")

    print(f"Semantic score: {evaluation['semantic_score']}")

    print(f"Relationship: {evaluation['relationship_type']}")

    print(f"Connection mode: {evaluation['connection_mode']}")

    print(f"Promotional sequence: {evaluation['best_sequence']}")

    print(f"Chronological order: {evaluation['chronological_order']}")

    print(f"Evidence A: {evaluation['evidence_a']}")

    print(f"Evidence B: {evaluation['evidence_b']}")

    print(f"Interpretation basis: {evaluation['interpretation_basis']}")

    print(f"Connection: {evaluation['connection_explanation']}")

    print(f"Sequence explanation: {evaluation['sequence_explanation']}")

    print(f"Manual review required: {evaluation['requires_manual_review']}")

    if evaluation["requires_manual_review"]:

        print(f"Review reason: {evaluation['manual_review_reason']}")


print("\n========== V4 SUMMARY ==========")

print(f"Evaluated: {len(verified_pairs)}/{len(test_pairs)}")

print(f"Classifications: {dict(counts)}")

print(
    f"Manual review required: "
    f"{manual_review_count}/{len(verified_pairs)}"
)

print("All deterministic regression checks passed.")

print("V4 semantic verification completed!")