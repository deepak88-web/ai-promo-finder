
import json
import argparse
from pathlib import Path

from src.llm.provider_router import get_provider


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROMPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "llm"
    / "prompts"
    / "candidate_evaluation.txt"
)

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "raw"


WEIGHTS = {
    "opening_hook": 0.20,
    "emotional_impact": 0.15,
    "suspense_curiosity": 0.20,
    "narrative_coherence": 0.15,
    "promotional_value": 0.20,
    "ending_strength": 0.10
}


def load_json(path):
    """Load JSON data from a file."""

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_prompt():
    """Load the candidate evaluation prompt."""

    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Evaluation prompt not found: {PROMPT_PATH}"
        )

    return PROMPT_PATH.read_text(encoding="utf-8")


def build_candidate_input(candidate_data):
    """Prepare candidate information for evaluation."""

    return {
        "episode": candidate_data["episode"],
        "duration_constraints": candidate_data["duration_constraints"],
        "candidates": candidate_data["candidates"]
    }


def validate_evaluation(result, candidate_data):
    """Validate model output and calculate scores independently."""

    if not isinstance(result, dict):
        raise ValueError(
            "Evaluation output must be a JSON object."
        )

    if result.get("episode") != candidate_data["episode"]:
        raise ValueError("Episode identifier mismatch.")

    evaluations = result.get("evaluated_candidates")

    if not isinstance(evaluations, list):
        raise ValueError(
            "evaluated_candidates must be a list."
        )

    expected_ids = {
        candidate["candidate_id"]
        for candidate in candidate_data["candidates"]
    }

    if not expected_ids:
        raise ValueError(
            "No valid candidates available for evaluation."
        )

    for index, item in enumerate(evaluations):

        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid evaluation at index {index}. "
                f"Expected a JSON object, but received "
                f"{type(item).__name__}: {item!r}"
            )

    returned_ids = [
        item.get("candidate_id")
        for item in evaluations
    ]

    if len(returned_ids) != len(set(returned_ids)):
        raise ValueError(
            "Duplicate candidate evaluations."
        )

    if set(returned_ids) != expected_ids:
        raise ValueError(
            "Groq must evaluate every candidate exactly once."
        )

    for item in evaluations:

        candidate_id = item["candidate_id"]
        scores = item.get("scores")

        if not isinstance(scores, dict):
            raise ValueError(
                f"Scores missing for {candidate_id}."
            )

        if set(scores) != set(WEIGHTS):
            raise ValueError(
                f"Incorrect score dimensions for {candidate_id}."
            )

        for criterion, score in scores.items():

            if (
                isinstance(score, bool)
                or not isinstance(score, int)
                or not 1 <= score <= 10
            ):
                raise ValueError(
                    f"Invalid {criterion} score for {candidate_id}."
                )

        calculated_score = round(
            sum(
                scores[key] * weight
                for key, weight in WEIGHTS.items()
            ),
            2
        )

        item["weighted_score"] = calculated_score

    # Python determines the final ranking.
    sorted_evaluations = sorted(
        evaluations,
        key=lambda item: (
            item["weighted_score"],
            item["candidate_id"]
        ),
        reverse=True
    )

    ranking = []

    for rank, item in enumerate(sorted_evaluations, start=1):

        ranking.append({
            "rank": rank,
            "candidate_id": item["candidate_id"],
            "weighted_score": item["weighted_score"],
            "reason": item.get("overall_assessment", "")
        })

    result["evaluated_candidates"] = evaluations
    result["ranking"] = ranking
    result["best_candidate"] = ranking[0]["candidate_id"]

    return result


def run_layer2_evaluation(episode_number=22, output_dir=OUTPUT_DIR):
    """Run Layer 2 evaluation for the requested episode."""

    candidates_path = (
        Path(output_dir)
        / f"candidates_episode{episode_number}.json"
    )

    output_path = (
        Path(output_dir)
        / f"layer2_episode{episode_number}_evaluation.json"
    )

    print("\n===== LAYER 2 CANDIDATE EVALUATION =====")

    candidate_data = load_json(candidates_path)
    system_prompt = load_prompt()

    expected_episode_id = f"EP{episode_number:03d}"

    if candidate_data.get("episode") != expected_episode_id:
        raise ValueError(
            f"Expected {expected_episode_id}, but candidate file "
            f"contains {candidate_data.get('episode')}."
        )

    if not candidate_data["candidates"]:
        raise ValueError(
            f"No valid candidates found for {expected_episode_id}."
        )

    user_input = json.dumps(
        build_candidate_input(candidate_data),
        ensure_ascii=False,
        separators=(",", ":")
    )

    print(f"Episode: {candidate_data['episode']}")
    print(
        f"Candidates to evaluate: "
        f"{len(candidate_data['candidates'])}"
    )

    provider_name, generate_json = get_provider("layer2")

    print(f"\nSending candidates to {provider_name.upper()}...")

    result = generate_json(
        system_prompt,
        user_input
    )

    print("\n===== DEBUG: GROQ RESPONSE =====")
    print("Response type:", type(result).__name__)

    if isinstance(result, dict):
        evaluations = result.get("evaluated_candidates")

        print(
            "Evaluated candidates type:",
            type(evaluations).__name__
        )

        if isinstance(evaluations, list):
            for index, item in enumerate(evaluations):
                print(
                    f"Item {index + 1} type:",
                    type(item).__name__
                )

    print("===== END DEBUG =====\n")

    validated_result = validate_evaluation(
        result,
        candidate_data
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            validated_result,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n===== LAYER 2 RESULTS =====")

    for item in validated_result["ranking"]:
        print(
            f"Rank {item['rank']}: "
            f"{item['candidate_id']} | "
            f"Score: {item['weighted_score']}/10"
        )

    print(
        f"\nBest candidate: "
        f"{validated_result['best_candidate']}"
    )

    print(f"Results saved at: {output_path}")

    return validated_result


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Evaluate promotional candidates for an episode."
    )

    parser.add_argument(
        "--episode",
        type=int,
        default=22,
        help="Episode number to evaluate (default: 22)"
    )

    args = parser.parse_args()

    if args.episode < 1 or args.episode > 50:
        parser.error(
            "Episode number must be between 1 and 50."
        )

    run_layer2_evaluation(args.episode)
