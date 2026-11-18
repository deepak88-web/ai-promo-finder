"""
Mock provider for testing the entire AI Promo Finder pipeline
with zero API keys, zero network calls, and deterministic outputs.
"""

import json
import re


def generate_json(system_prompt, user_input, api_key=None, model=None, base_url=None, **kwargs):
    # Detect request type from system prompt or user input
    combined = (system_prompt + " " + user_input).lower()

    # 1. Layer 1 Event Identification
    if "dramatic_events" in combined or "event_category" in combined or "event identification" in combined:
        ep_match = re.search(r'"episode_id":\s*"([^"]+)"', user_input) or re.search(r'"episode":\s*"([^"]+)"', user_input)
        episode_id = ep_match.group(1) if ep_match else "EP001"
        event_ids = re.findall(r'"event_id":\s*"([^"]+)"', user_input)
        if not event_ids:
            event_ids = [f"{episode_id}_S001_E001", f"{episode_id}_S001_E002"]

        selected_ids = event_ids[:min(3, len(event_ids))]
        return {
            "episode": episode_id,
            "dramatic_events": [
                {
                    "selection_id": f"{episode_id}_D001",
                    "event_ids": selected_ids,
                    "event_category": "confrontation",
                    "importance": 5,
                    "emotional_tone": "suspenseful",
                    "description": "High stakes dramatic revelation and confrontation.",
                    "promotional_reason": "Captures viewer curiosity and intense character conflict.",
                    "hook_potential": "strong",
                    "ending_potential": "strong",
                    "requires_context": False,
                }
            ],
        }

    # 2. Layer 2 Candidate Evaluation
    if "evaluated_candidates" in combined or "opening_hook" in combined and "candidates" in combined:
        ep_match = re.search(r'"episode":\s*"([^"]+)"', user_input)
        episode_id = ep_match.group(1) if ep_match else "EP001"
        candidate_ids = re.findall(r'"candidate_id":\s*"([^"]+)"', user_input)
        if not candidate_ids:
            candidate_ids = [f"{episode_id}_C001"]

        evaluated = []
        for index, cid in enumerate(candidate_ids, start=1):
            score = 8.5 - (index - 1) * 0.5
            evaluated.append({
                "candidate_id": cid,
                "scores": {
                    "opening_hook": 8,
                    "emotional_impact": 8,
                    "suspense_curiosity": 9,
                    "narrative_coherence": 8,
                    "promotional_value": 9,
                    "ending_strength": 8,
                },
                "weighted_score": score,
                "strengths": ["Immediate emotional hook", "Clear stakes"],
                "weaknesses": ["Could trim early dialogue slightly"],
                "overall_assessment": "Highly engaging candidate with strong promotional pull.",
            })

        ranking = [
            {"rank": i + 1, "candidate_id": item["candidate_id"], "weighted_score": item["weighted_score"], "reason": "Strong overall tension"}
            for i, item in enumerate(evaluated)
        ]
        return {
            "episode": episode_id,
            "evaluated_candidates": evaluated,
            "ranking": ranking,
            "best_candidate": evaluated[0]["candidate_id"],
        }

    # 3. Promo Evaluation
    if "evaluations" in combined or "promo_id" in combined:
        promo_ids = list(dict.fromkeys(re.findall(r'"promo_id":\s*"([^"]+)"', user_input)))
        if not promo_ids:
            promo_ids = ["PROMO_EP001_C001"]

        evals = []
        for pid in promo_ids:
            evals.append({
                "promo_id": pid,
                "opening_hook": 8.0,
                "standalone_coherence": 8.0,
                "narrative_flow": 8.0,
                "emotional_impact": 8.0,
                "cliffhanger_effectiveness": 8.0,
                "promotional_appeal": 8.0,
                "overall_score": 8.0,
                "hook_explanation": "Hook delivers sharp immediate conflict within the first 3 seconds.",
                "coherence_explanation": "Central dilemma and character stakes are readily apparent without prior context.",
                "flow_explanation": "Scenes progress with natural escalating momentum.",
                "cliffhanger_explanation": "Ends on a memorable unanswered question.",
                "one_line_pitch": "A high-tension moment that demands viewers find out what happens next.",
                "strengths": ["Clear stakes", "Compelling final cutoff"],
                "weaknesses": ["Minor ambient pause"],
                "improvement_suggestion": "Tighten opening second for extra punch.",
                "decision": "recommend",
            })

        return {"evaluations": evals}

    # 4. Fallback Generic JSON
    return {"status": "ok", "message": "Mock provider response"}
