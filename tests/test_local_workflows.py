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
            "decision": "revise",
        }]
    }
    validated = validate_evaluation_response(json.dumps(response), {"P1"})
    assert validated["P1"]["overall_score"] == 5.5
