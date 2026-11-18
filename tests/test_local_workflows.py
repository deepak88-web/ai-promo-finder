import json
import zipfile

from src.promo_composer.promo_evaluator import (
    calculate_overall_score,
    calculate_evaluation_fingerprint,
    validate_evaluation_response,
)
from src.llm.provider_router import get_provider

from src.parser.script_parser import parse_input_pack
from src.promo_composer.promo_validator import validate_evidence_against_source
from src.promo_composer.segment_selector import (
    build_verified_hub_montages,
    select_same_episode_combinations,
)


def _candidate(candidate_id, start, end, event_id, event_start, event_end):
    event = {
        "event_id": event_id,
        "text": f"Evidence {event_id}",
        "start_time": event_start,
        "end_time": event_end,
    }
    return {
        "candidate_id": candidate_id,
        "segment_id": f"SEG_{candidate_id}",
        "source_type": "layer2_candidate",
        "episode": "EP001",
        "start_time": start,
        "end_time": end,
        "duration": end - start,
        "event_ids": [event_id],
        "source_events": [event],
        "selection_score": 80,
    }


def test_same_episode_composer_emits_three_segment_cutlist():
    candidates = [
        _candidate("EP001_C001", 0, 25, "E1", 1, 2),
        _candidate("EP001_C002", 30, 55, "E2", 40, 42),
        _candidate("EP001_C003", 60, 85, "E3", 80, 83),
    ]
    combinations = select_same_episode_combinations(candidates)
    triples = [item for item in combinations if item["segment_count"] == 3]
    assert triples
    assert 20 <= triples[0]["combined_source_duration"] <= 60
    assert len(triples[0]["ordered_segments"]) == 3
    assert triples[0]["requires_manual_review"] is True


def test_verified_hub_montage_keeps_three_timestamps_and_pair_refs():
    hub = {
        "anchor_event_id": "H",
        "episode": "EP001",
        "start_time": 0,
        "end_time": 10,
        "duration": 10,
        "source_events": [{"event_id": "H", "text": "hub", "start_time": 2, "end_time": 3}],
    }
    spoke1 = {
        "anchor_event_id": "A",
        "episode": "EP002",
        "start_time": 10,
        "end_time": 30,
        "duration": 20,
        "source_events": [{"event_id": "A", "text": "one", "start_time": 20, "end_time": 21}],
    }
    spoke2 = {
        "anchor_event_id": "B",
        "episode": "EP003",
        "start_time": 30,
        "end_time": 50,
        "duration": 20,
        "source_events": [{"event_id": "B", "text": "two", "start_time": 40, "end_time": 41}],
    }
    pairs = [
        {"combination_id": "P1", "semantic_score": 80, "ordered_segments": [hub, spoke1]},
        {"combination_id": "P2", "semantic_score": 70, "ordered_segments": [hub, spoke2]},
    ]
    events = {
        "H": {"event_id": "H", "episode": "EP001", "start_time": 2, "end_time": 3, "text": "hub"},
        "A": {"event_id": "A", "episode": "EP002", "start_time": 20, "end_time": 21, "text": "one"},
        "B": {"event_id": "B", "episode": "EP003", "start_time": 40, "end_time": 41, "text": "two"},
    }
    drafts = build_verified_hub_montages(pairs, events)
    assert len(drafts) == 1
    assert drafts[0]["segment_count"] == 3
    assert drafts[0]["connection_evidence_pair_ids"] == ["P1", "P2"]
    assert 20 <= drafts[0]["combined_source_duration"] <= 60


def test_missing_evidence_timestamp_is_explicit_warning():
    warnings = []
    promo = {"segments": [{}]}
    segment = {
        "episode": "EP001",
        "source_events": [{
            "event_id": "E1",
            "start_time": 1,
            "end_time": 2,
            "text": "A clear source line.",
        }],
    }
    validate_evidence_against_source(
        promo=promo,
        evidence={"evidence_event_id": "E1", "timestamp": None, "evidence_text": "A clear source line.", "episode": "EP001"},
        expected_segment=segment,
        window_start=0,
        window_end=3,
        evidence_type="HOOK",
        warnings=warnings,
    )
    assert any(item["code"] == "HOOK_TIMESTAMP_MISSING" for item in warnings)


def test_parser_accepts_a_new_zip_pack(tmp_path):
    script = """EPISODE NUMBER: 1
EPISODE LOGLINE: A new test episode
CONTINUITY NOTES: None
--- SCRIPT START ---
SCENE 1
SCENE HEADING: INT. ROOM - DAY
SCENE START: 00:00.00
SCENE END: 00:04.00
**ACTION:**
Start: (00:00.00) | End: (00:02.00)
Maya enters the room.
--- SCRIPT END ---
"""
    archive_path = tmp_path / "new_pack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Episode1.txt", script)
    episodes = parse_input_pack(archive_path)
    assert len(episodes) == 1
    assert episodes[0]["episode"] == "1"
    assert episodes[0]["scenes"][0]["events"]


def test_provider_router_supports_promo_evaluator_provider(monkeypatch):
    monkeypatch.setenv("PROMO_EVALUATION_PROVIDER", "groq")
    provider_name, generator = get_provider("promo_evaluation")
    assert provider_name == "groq"
    assert callable(generator)


def test_evaluator_computes_weighted_score_and_fingerprints_provider():
    values = {
        "opening_hook": 10,
        "standalone_coherence": 8,
        "narrative_flow": 6,
        "emotional_impact": 4,
        "cliffhanger_effectiveness": 2,
        "promotional_appeal": 0,
    }
    assert calculate_overall_score(values) == 5.5
    assert calculate_evaluation_fingerprint("prompt", "gemini", "m1") != calculate_evaluation_fingerprint("prompt", "groq", "m1")
    response = {
        "evaluations": [{
            "promo_id": "P1",
            **values,
            "overall_score": 100,
            "hook_explanation": "h",
            "coherence_explanation": "c",
            "flow_explanation": "f",
            "cliffhanger_explanation": "e",
            "one_line_pitch": "pitch",
            "strengths": [],
            "weaknesses": [],
            "improvement_suggestion": "trim",
            "decision": "recommend",
        }]
    }
    validated = validate_evaluation_response(json.dumps(response), {"P1"})
    assert validated["P1"]["overall_score"] == 5.5
    # Decision is deterministically calculated from score (5.5 is in 5.0 <= s < 7.0 range -> revise)
    assert validated["P1"]["decision"] == "revise"


def test_parser_timestamp_formats():
    from src.parser.script_parser import to_seconds
    assert to_seconds("01:23.45") == 83.45
    assert to_seconds("00:01:23.45") == 83.45
    assert to_seconds("01:23") == 83.0
    assert to_seconds(45.5) == 45.5
    assert to_seconds("invalid") == 0.0


def test_evaluator_decision_logic():
    # Test score >= 7.0 -> recommend
    rec_values = {
        "opening_hook": 8.0,
        "standalone_coherence": 8.0,
        "narrative_flow": 7.0,
        "emotional_impact": 7.0,
        "cliffhanger_effectiveness": 8.0,
        "promotional_appeal": 7.0,
    }
    resp1 = {
        "evaluations": [{
            "promo_id": "REC_1",
            **rec_values,
            "hook_explanation": "h", "coherence_explanation": "c",
            "flow_explanation": "f", "cliffhanger_explanation": "e",
            "one_line_pitch": "p", "strengths": [], "weaknesses": [],
            "improvement_suggestion": "none", "decision": "reject"  # Should be overridden by deterministic score
        }]
    }
    v1 = validate_evaluation_response(json.dumps(resp1), {"REC_1"})
    assert v1["REC_1"]["overall_score"] >= 7.0
    assert v1["REC_1"]["decision"] == "recommend"

    # Test standalone coherence < 5.0 -> downgrade to revise
    downgrade_values = dict(rec_values)
    downgrade_values["standalone_coherence"] = 4.0
    resp2 = {
        "evaluations": [{
            "promo_id": "REC_2",
            **downgrade_values,
            "hook_explanation": "h", "coherence_explanation": "c",
            "flow_explanation": "f", "cliffhanger_explanation": "e",
            "one_line_pitch": "p", "strengths": [], "weaknesses": [],
            "improvement_suggestion": "none", "decision": "recommend"
        }]
    }
    v2 = validate_evaluation_response(json.dumps(resp2), {"REC_2"})
    assert v2["REC_2"]["decision"] == "revise"


def test_mock_provider_via_router():
    from src.llm.provider_router import get_provider
    p_name, gen = get_provider("layer1", provider_override="mock")
    assert p_name == "mock"
    result = gen("system", "user")
    assert isinstance(result, dict)
    assert result.get("status") == "ok"


def test_layer2_input_includes_dialogue():
    from src.llm.layer2_candidate_evaluation import build_candidate_input
    candidate = {
        "candidate_id": "EP001_C001",
        "scene_number": 1,
        "start_time": 0.0,
        "end_time": 30.0,
        "duration": 30.0,
        "dialogue_excerpt": "MAYA: The firewall was breached!\nKABIR: Calm down.",
        "source_events": [
            {"event_id": "E1", "type": "dialogue", "speaker": "MAYA", "text": "The firewall was breached!"}
        ]
    }
    formatted = build_candidate_input(candidate)
    assert "dialogue_and_action_excerpt" in formatted["candidates"][0]
    assert "The firewall was breached!" in formatted["candidates"][0]["dialogue_and_action_excerpt"]


def test_promo_validator_genuine_hook_cliffhanger():
    from src.promo_composer.promo_validator import validate_single_promo

    # Promo without hook identified
    bad_promo = {
        "promo_id": "PROMO_TEST",
        "construction_type": "single_continuous_segment",
        "segment_count": 1,
        "total_duration": 30.0,
        "episodes": ["EP001"],
        "segments": [{
            "segment_id": "SEG_001",
            "segment_order": 1,
            "episode": "EP001",
            "start_time": 0.0,
            "end_time": 30.0,
            "duration": 30.0,
            "event_ids": ["E1"],
            "source_events": [{"event_id": "E1", "start_time": 0.0, "end_time": 10.0, "text": "test"}]
        }],
        "hook": {"identified": False},
        "cliffhanger": {"identified": False},
    }
    validated = validate_single_promo(bad_promo)
    warning_codes = [w["code"] for w in validated["validation_warnings"]]
    assert "NO_HOOK_IN_OPENING" in warning_codes
    assert "NO_CLIFFHANGER_AT_ENDING" in warning_codes
    # Blanket warning STANDALONE_COHERENCE_PENDING must NOT be present
    assert "STANDALONE_COHERENCE_PENDING" not in warning_codes
    assert validated["is_valid"] is True
    assert validated["requires_manual_review"] is True


def test_unified_output_and_ranking_export(tmp_path):
    from src.promo_composer.promo_ranker import rank_and_export
    eval_data = {
        "evaluated_promos": [{
            "promo_id": "P_001",
            "episodes": ["EP001"],
            "actual_duration": 35.5,
            "segments": [{
                "segment_order": 1,
                "episode": "EP001",
                "start_time": 10.0,
                "end_time": 45.5,
                "duration": 35.5,
            }],
            "hook": {"evidence_text": "Shocking discovery"},
            "cliffhanger": {"evidence_text": "Ticking bomb"},
            "validation_warnings": [],
            "evaluation": {
                "opening_hook": 9.0,
                "standalone_coherence": 8.5,
                "narrative_flow": 8.0,
                "emotional_impact": 8.0,
                "cliffhanger_effectiveness": 9.0,
                "promotional_appeal": 8.5,
                "overall_score": 8.55,
                "decision": "recommend",
                "one_line_pitch": "A high-stakes espionage thriller.",
                "strengths": ["Strong hook", "Great ending"],
                "weaknesses": [],
                "improvement_suggestion": "None",
            }
        }]
    }
    in_file = tmp_path / "promo_evaluation.json"
    in_file.write_text(json.dumps(eval_data), encoding="utf-8")
    out_dir = tmp_path / "final"

    results = rank_and_export(input_path=in_file, output_dir=out_dir)
    assert (out_dir / "final_promos.json").exists()
    assert (out_dir / "final_promos.csv").exists()
    assert (out_dir / "ranked_promos.json").exists()
    assert (out_dir / "ranked_promos.csv").exists()

    final_promos = json.loads((out_dir / "final_promos.json").read_text(encoding="utf-8"))
    assert len(final_promos) == 1
    assert final_promos[0]["rank"] == 1
    assert final_promos[0]["segments"][0]["start_time"] == "00:10.00"
    assert final_promos[0]["segments"][0]["end_time"] == "00:45.50"


def test_end_to_end_mock_pipeline(tmp_path):
    from src.pipeline.run_new_input_pack import run as run_pack
    from pathlib import Path

    sample_zip = Path("sample_data/sample_screenplays.zip")
    assert sample_zip.exists()

    out_dir = tmp_path / "test_run"
    result = run_pack(
        input_path=sample_zip,
        output_dir=out_dir,
        evaluate=True,
        provider="mock",
    )
    assert result["episodes_in_pack"] == 2
    assert result["episodes_failed"] == 0
    assert (out_dir / "parsed_episodes.json").exists()
    assert (out_dir / "raw" / "candidates_episode1.json").exists()
    assert (out_dir / "raw" / "layer2_episode1_evaluation.json").exists()
    assert (out_dir / "raw" / "promo_validation_results.json").exists()
    assert (out_dir / "final" / "final_promos.json").exists()
    assert (out_dir / "final" / "final_promos.csv").exists()


def test_e2e_full_promo_lifecycle_and_deliverables(tmp_path):
    """
    Comprehensive End-to-End Test Case:
    Tests complete lifecycle from screenplay parsing to final ranked promo deliverables.
    Verifies 20-60s duration rules, segment timestamp formatting (MM:SS.hh),
    hook/cliffhanger grounding, and CSV/JSON export schemas.
    """
    import csv
    from src.pipeline.run_new_input_pack import run as run_pack
    from pathlib import Path

    sample_zip = Path("sample_data/sample_screenplays.zip")
    assert sample_zip.exists(), "Sample screenplays pack must be present"

    e2e_dir = tmp_path / "e2e_deliverable_test"
    run_result = run_pack(
        input_path=sample_zip,
        output_dir=e2e_dir,
        evaluate=True,
        provider="mock",
    )

    assert run_result["episodes_in_pack"] == 2
    assert run_result["episodes_failed"] == 0

    # 1. Verify intermediate outputs
    assert (e2e_dir / "parsed_episodes.json").exists()
    assert (e2e_dir / "reports" / "master_candidate_results.csv").exists()
    assert (e2e_dir / "reports" / "global_ranking.csv").exists()
    assert (e2e_dir / "raw" / "promo_builder_results.json").exists()
    assert (e2e_dir / "raw" / "promo_validation_results.json").exists()
    assert (e2e_dir / "raw" / "promo_evaluation.json").exists()

    # 2. Verify final deliverables
    final_json_path = e2e_dir / "final" / "final_promos.json"
    final_csv_path = e2e_dir / "final" / "final_promos.csv"
    assert final_json_path.exists()
    assert final_csv_path.exists()

    final_promos = json.loads(final_json_path.read_text(encoding="utf-8"))
    assert isinstance(final_promos, list)
    assert len(final_promos) > 0, "At least one promo should be generated and ranked"

    # Verify first promo meets all assignment requirements
    top_promo = final_promos[0]
    assert "rank" in top_promo and top_promo["rank"] == 1
    assert "promo_id" in top_promo
    assert "total_duration" in top_promo
    assert 20.0 <= top_promo["total_duration"] <= 60.0, "Promo duration must be between 20 and 60 seconds"
    assert "segments" in top_promo and len(top_promo["segments"]) >= 1

    # Check segment timestamp formatting
    seg0 = top_promo["segments"][0]
    assert ":" in seg0["start_time"], "Start time must be formatted MM:SS.hh"
    assert ":" in seg0["end_time"], "End time must be formatted MM:SS.hh"
    assert seg0["duration"] > 0

    # Check hook, cliffhanger, score, decision
    assert "hook" in top_promo
    assert "cliffhanger" in top_promo
    assert "overall_score" in top_promo
    assert "decision" in top_promo
    assert top_promo["decision"] in {"recommend", "revise", "reject"}

    # 3. Verify final CSV format matches schema
    with final_csv_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == len(final_promos)
        assert "rank" in rows[0]
        assert "promo_id" in rows[0]
        assert "total_duration" in rows[0]
        assert "segments" in rows[0]
        assert "one_line_pitch" in rows[0]
        assert "overall_score" in rows[0]
        assert "decision" in rows[0]


def test_hybrid_multi_provider_routing_pipeline(tmp_path):
    """
    Verifies that the pipeline correctly accepts separate per-layer providers,
    models, and keys (e.g. Layer 1 = mock, Layer 2 = mock, Promo Eval = mock).
    """
    from src.pipeline.run_new_input_pack import run as run_pack
    from pathlib import Path

    sample_zip = Path("sample_data/sample_screenplays.zip")
    assert sample_zip.exists()

    out_dir = tmp_path / "hybrid_run"
    result = run_pack(
        input_path=sample_zip,
        output_dir=out_dir,
        evaluate=True,
        layer1_provider="mock",
        layer1_model="mock-l1-model",
        layer1_key="mock-l1-key",
        layer2_provider="mock",
        layer2_model="mock-l2-model",
        layer2_key="mock-l2-key",
        promo_eval_provider="mock",
        promo_eval_model="mock-pe-model",
        promo_eval_key="mock-pe-key",
    )
    assert result["episodes_in_pack"] == 2
    assert result["episodes_failed"] == 0
    assert result["valid_promos"] >= 1
    assert (out_dir / "final" / "final_promos.json").exists()
    assert (out_dir / "final" / "final_promos.csv").exists()



