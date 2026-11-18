
import streamlit as st
import pandas as pd
from pathlib import Path
import json
import tempfile
from datetime import datetime

from src.promo_composer.promo_builder import build_multi_segment_promo
from src.promo_composer.promo_validator import validate_promo


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="AI Promo Finder",
    page_icon="🎬",
    layout="wide"
)

PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
RAW_DIR = PROJECT_ROOT / "outputs" / "raw"


# --------------------------------------------------
# LOAD CONSOLIDATED DATA
# --------------------------------------------------

@st.cache_data
def load_data():
    master = pd.read_csv(
        REPORT_DIR / "master_candidate_results.csv"
    )

    ranking = pd.read_csv(
        REPORT_DIR / "global_ranking.csv"
    )

    episodes = pd.read_csv(
        REPORT_DIR / "episode_summary.csv"
    )

    return master, ranking, episodes


@st.cache_data
def load_optional_json(filename):
    path = RAW_DIR / filename
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


try:
    master_df, ranking_df, episode_df = load_data()
except FileNotFoundError as error:
    st.error(f"Required report file not found: {error}")
    st.info(
        "Run the consolidation script first to generate "
        "the required CSV reports."
    )
    st.stop()


# --------------------------------------------------
# SIDEBAR NAVIGATION
# --------------------------------------------------

st.sidebar.title("🎬 AI Promo Finder")
st.sidebar.caption("AI-powered promotional clip discovery")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Global Rankings",
        "Episode Explorer",
        "Candidate Details",
        "Candidate Comparison",
        "Promo Composer",
        "Cross-Episode Discovery",
        "New Input Processing",
        "Promo Quality Review",
    ]
)


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":

    st.title("AI Promo Finder")
    st.write(
        "Discover the most engaging promotional moments "
        "across screenplay episodes."
    )

    total_episodes = episode_df["episode"].nunique()
    total_candidates = len(master_df)
    evaluated_candidates = (
        master_df["weighted_score"].notna().sum()
    )

    average_score = master_df["weighted_score"].mean()
    best_candidate = ranking_df.iloc[0]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Episodes Processed", total_episodes)
    col2.metric("Total Candidates", total_candidates)
    col3.metric("Evaluated Candidates", evaluated_candidates)
    col4.metric("Average Score", f"{average_score:.2f}/10")

    st.divider()

    st.subheader("🏆 Best Promotional Candidate")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            f"### {best_candidate['candidate_id']}"
        )
        st.write(
            f"Episode: **{best_candidate['episode']}**"
        )
        st.write(
            f"Weighted Score: **{best_candidate['weighted_score']}/10**"
        )

    with col2:
        st.metric(
            "Top Candidate Score",
            f"{best_candidate['weighted_score']}/10"
        )

    st.divider()

    st.subheader("Top 10 Promotional Candidates")

    st.dataframe(
        ranking_df[
            [
                "global_rank",
                "episode",
                "candidate_id",
                "duration",
                "weighted_score"
            ]
        ].head(10),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Candidate Score Distribution")

    st.bar_chart(
        ranking_df.set_index("candidate_id")["weighted_score"],
        height=300
    )

# --------------------------------------------------
# GLOBAL RANKINGS
# --------------------------------------------------

elif page == "Global Rankings":

    st.title("Global Candidate Rankings")

    min_score = st.slider(
        "Minimum weighted score",
        min_value=0.0,
        max_value=10.0,
        value=0.0,
        step=0.25
    )

    selected_episode = st.selectbox(
        "Filter by episode",
        ["All Episodes"] + sorted(
            ranking_df["episode"].unique().tolist()
        )
    )

    filtered_df = ranking_df[
        ranking_df["weighted_score"] >= min_score
    ]

    if selected_episode != "All Episodes":
        filtered_df = filtered_df[
            filtered_df["episode"] == selected_episode
        ]
    st.write(f"Showing **{len(filtered_df)} candidates**")

    display_columns = [
        "global_rank",
        "episode",
        "candidate_id",
        "scene_number",
        "start_time",
        "end_time",
        "duration",
        "weighted_score"
    ]

    st.dataframe(
        filtered_df[display_columns],
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download Filtered Rankings",
        data=filtered_df.to_csv(index=False).encode("utf-8"),
        file_name="filtered_global_ranking.csv",
        mime="text/csv"
    )


# --------------------------------------------------
# EPISODE EXPLORER
# --------------------------------------------------

elif page == "Episode Explorer":

    st.title("Episode Explorer")

    selected_episode = st.selectbox(
        "Select Episode",
        sorted(master_df["episode"].unique())
    )

    episode_candidates = master_df[
        master_df["episode"] == selected_episode
    ].sort_values(
        "weighted_score",
        ascending=False
    )

    st.subheader(f"Results for {selected_episode}")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Total Candidates",
        len(episode_candidates)
    )

    col2.metric(
        "Best Score",
        f"{episode_candidates['weighted_score'].max():.2f}"
    )

    best = episode_candidates.iloc[0]

    col3.metric(
        "Best Candidate",
        best["candidate_id"]
    )

    st.divider()

    st.dataframe(
        episode_candidates[
            [
                "candidate_id",
                "scene_number",
                "start_time",
                "end_time",
                "duration",
                "event_categories",
                "weighted_score"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Candidate Descriptions")

    for _, candidate in episode_candidates.iterrows():

        with st.expander(
            f"{candidate['candidate_id']} — "
            f"Score: {candidate['weighted_score']}"
        ):
            st.write(
                f"**Duration:** {candidate['duration']} seconds"
            )

            st.write(
                f"**Time:** {candidate['start_time']} – "
                f"{candidate['end_time']} seconds"
            )

            st.write(
                f"**Categories:** {candidate['event_categories']}"
            )

            st.write("**Description:**")
            st.write(candidate["descriptions"])


# --------------------------------------------------
# CANDIDATE DETAILS
# --------------------------------------------------

elif page == "Candidate Details":

    st.title("Candidate Evaluation Details")

    selected_candidate = st.selectbox(
        "Select Candidate",
        ranking_df["candidate_id"].tolist()
    )

    candidate = master_df[
        master_df["candidate_id"] == selected_candidate
    ].iloc[0]

    st.subheader(selected_candidate)

    col1, col2, col3 = st.columns(3)

    col1.metric("Episode", candidate["episode"])
    col2.metric("Duration", f"{candidate['duration']} sec")
    col3.metric(
        "Weighted Score",
        f"{candidate['weighted_score']}/10"
    )

    st.divider()

    st.subheader("Evaluation Scores")

    score_fields = [
        "opening_hook",
        "emotional_impact",
        "suspense_curiosity",
        "narrative_coherence",
        "promotional_value",
        "ending_strength"
    ]

    score_data = pd.DataFrame({
        "Evaluation Criteria": score_fields,
        "Score": [
            candidate[field] for field in score_fields
        ]
    })

    st.bar_chart(
        score_data.set_index("Evaluation Criteria")
    )

    st.divider()

    st.subheader("Candidate Description")
    st.write(candidate["descriptions"])

    st.subheader("Strengths")
    st.write(candidate["strengths"])

    st.subheader("Weaknesses")
    st.write(candidate["weaknesses"])

    st.subheader("Overall Assessment")
    st.info(candidate["overall_assessment"])

    st.subheader("Event Categories")
    st.write(candidate["event_categories"])


# --------------------------------------------------
# CANDIDATE COMPARISON
# --------------------------------------------------

elif page == "Candidate Comparison":

    st.title("Candidate Comparison")
    candidate_ids = ranking_df["candidate_id"].dropna().astype(str).tolist()
    if len(candidate_ids) < 2:
        st.info("At least two ranked candidates are needed for comparison.")
    else:
        left, right = st.columns(2)
        first_id = left.selectbox("First candidate", candidate_ids, index=0)
        second_default = 1 if candidate_ids[0] == first_id else 0
        second_id = right.selectbox(
            "Second candidate", candidate_ids, index=second_default,
            key="comparison_candidate_two",
        )
        if first_id == second_id:
            st.warning("Choose two different candidates to compare.")
        else:
            selected = master_df[
                master_df["candidate_id"].astype(str).isin([first_id, second_id])
            ].set_index("candidate_id").loc[[first_id, second_id]]
            score_fields = [
                field for field in [
                    "opening_hook", "emotional_impact", "suspense_curiosity",
                    "narrative_coherence", "promotional_value", "ending_strength",
                    "weighted_score",
                ] if field in selected.columns
            ]
            st.subheader("Scores")
            st.dataframe(selected[score_fields].T, use_container_width=True)
            detail_cols = [
                field for field in ["episode", "duration", "event_categories", "descriptions",
                                    "strengths", "weaknesses", "overall_assessment"]
                if field in selected.columns
            ]
            st.subheader("Candidate details")
            st.dataframe(selected[detail_cols].T, use_container_width=True)


# --------------------------------------------------
# PROMO QUALITY REVIEW
# --------------------------------------------------

elif page == "New Input Processing":

    st.title("Process a New Screenplay Pack")
    st.write("Upload a ZIP pack or one or more TXT screenplays. Processing reuses the configured Layer 1 and Layer 2 providers and saves a separate run folder.")
    st.warning("Starting a run sends screenplay text to the configured AI providers and may use their API quota. Nothing runs until you press the button.")
    uploads = st.file_uploader(
        "Screenplay ZIP or TXT files",
        type=["zip", "txt"],
        accept_multiple_files=True,
    )
    include_promo_evaluation = st.checkbox(
        "Also run full-promo evaluation after composition",
        value=False,
        help="Uses the PROMO_EVALUATION_PROVIDER configured in .env. This adds model calls.",
    )
    if st.button("Process uploaded pack", disabled=not uploads):
        with tempfile.TemporaryDirectory(prefix="ai_promo_upload_") as temp_root:
            temp_root = Path(temp_root)
            if len(uploads) == 1 and uploads[0].name.lower().endswith(".zip"):
                input_path = temp_root / uploads[0].name
                input_path.write_bytes(uploads[0].getvalue())
            else:
                input_path = temp_root / "screenplays"
                input_path.mkdir()
                for upload in uploads:
                    if not upload.name.lower().endswith(".txt"):
                        st.error("Upload either one ZIP pack or one or more TXT files.")
                        st.stop()
                    (input_path / Path(upload.name).name).write_bytes(upload.getvalue())
            run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
            output_dir = PROJECT_ROOT / "outputs" / "new_input_runs" / run_id
            try:
                from src.pipeline.run_new_input_pack import run as run_new_pack
                with st.spinner("Parsing and processing the screenplay pack..."):
                    result = run_new_pack(
                        input_path,
                        output_dir,
                        evaluate=include_promo_evaluation,
                    )
                st.success("Processing finished. Outputs are saved locally.")
                st.json(result)
                st.code(str(output_dir))
            except Exception as error:
                st.error(f"The run stopped: {error}")
                st.caption("Inspect run_failures.json and the per-episode raw outputs for partial progress.")


# --------------------------------------------------
# PROMO QUALITY REVIEW
# --------------------------------------------------

elif page == "Promo Composer":

    st.title("Multi-Segment Promo Composer")
    st.caption("Review a generated composition, adjust its order, and download a timestamped JSON draft.")
    selection_data = load_optional_json("expanded/promo_segment_selection.json")
    if not selection_data:
        st.info("Run `python -m src.promo_composer.run_promo_pipeline --expanded` to build composition candidates.")
    else:
        combo_groups = {
            "Same-episode montages": selection_data.get("same_episode_combinations", []),
            "V4-verified cross-episode pairs": selection_data.get("cross_episode_combinations", []),
            "V4 hub montages (manual review)": selection_data.get("verified_hub_montages", []),
        }
        options = []
        indexed = {}
        for group_name, group in combo_groups.items():
            for combo in group:
                key = f"{group_name} | {combo.get('combination_id')}"
                options.append(key)
                indexed[key] = combo
        if not options:
            st.info("No composition candidates are available.")
        else:
            chosen_key = st.selectbox("Composition candidate", options)
            combo = indexed[chosen_key]
            source_segments = combo.get("ordered_segments", [])
            st.write(combo.get("connection_explanation", ""))
            if combo.get("connection_evidence_pair_ids"):
                st.write("Frozen V4 pair evidence:", ", ".join(combo["connection_evidence_pair_ids"]))
            if combo.get("requires_manual_review"):
                st.warning("This composition requires human editorial review and fresh evaluator scoring before publication.")
            st.write(f"Source duration: **{combo.get('combined_source_duration')} seconds** across **{len(source_segments)} segments**")

            st.subheader("Set viewing order")
            preserve_verified_order = bool(
                combo.get("connection_evidence_pair_ids")
                or combo.get("source_type") in {"cross_episode_pair", "verified_hub_montage"}
            )
            if preserve_verified_order:
                st.info("The cross-episode order is fixed to the sequence supported by the saved evidence.")
            positions = []
            for index, segment in enumerate(source_segments, start=1):
                options_order = list(range(1, len(source_segments) + 1))
                positions.append(st.selectbox(
                    f"Position for {segment.get('segment_id') or segment.get('candidate_id')} ({segment.get('episode')})",
                    options_order,
                    index=index - 1,
                    key=f"composer_pos_{combo.get('combination_id')}_{index}",
                    disabled=preserve_verified_order,
                ))
            if len(set(positions)) != len(positions):
                st.error("Each segment needs a unique position.")
            else:
                ordered = [segment for _, segment in sorted(zip(positions, source_segments), key=lambda pair: pair[0])]
                draft_combo = dict(combo)
                draft_combo["ordered_segments"] = ordered
                draft = build_multi_segment_promo(draft_combo)
                if draft:
                    draft["requires_manual_review"] = bool(
                        combo.get("requires_manual_review") or ordered != source_segments
                    )
                    if ordered != source_segments:
                        draft["sequence_explanation"] = (
                            "The viewing order was changed interactively; review all transitions and reevaluate narrative flow."
                        )
                    checked = validate_promo(draft)
                    st.subheader("Promo preview")
                    a, b, c = st.columns(3)
                    a.metric("Duration", f"{checked.get('actual_duration')} sec")
                    b.metric("Segments", checked.get("segment_count"))
                    c.metric("Structural status", checked.get("validation_status"))
                    st.dataframe(pd.DataFrame([
                        {
                            "Order": part.get("segment_order"),
                            "Episode": part.get("episode"),
                            "Start": part.get("start_time"),
                            "End": part.get("end_time"),
                            "Duration": part.get("duration"),
                            "Evidence text": part.get("text", ""),
                        }
                        for part in checked.get("segments", [])
                    ]), use_container_width=True, hide_index=True)
                    st.caption("This is a candidate cut list. It does not prove the hook, cliffhanger, or standalone coherence; those need evaluator and human review.")
                    st.download_button(
                        "Download promo draft JSON",
                        data=json.dumps(checked, ensure_ascii=False, indent=2),
                        file_name=f"{checked['promo_id']}_draft.json",
                        mime="application/json",
                    )
                else:
                    st.error("This combination does not satisfy the 20-60 second duration rule.")


# --------------------------------------------------
# CROSS-EPISODE DISCOVERY
# --------------------------------------------------

elif page == "Cross-Episode Discovery":

    st.title("Cross-Episode Discovery")
    st.caption("Connections are grounded only in the saved Semantic Verifier V4 output. No new verification calls are made here.")
    selection_data = load_optional_json("expanded/promo_segment_selection.json")
    if not selection_data:
        st.info("Run the expanded local pipeline to load the frozen pair audit.")
    else:
        audit = selection_data.get("verified_pair_audit", [])
        st.metric("Frozen V4 pairs inspected", len(audit))
        audit_rows = [{
            "Pair": item.get("pair_id"),
            "Episodes": f"{item.get('event_a_episode')} → {item.get('event_b_episode')}",
            "Class": item.get("classification"),
            "Score": item.get("semantic_score"),
            "Connection": item.get("connection_mode"),
            "Sequence": item.get("best_sequence"),
            "Selected as two-part promo": item.get("selected_as_pair"),
            "Manual review": item.get("requires_manual_review"),
        } for item in audit]
        if audit_rows:
            st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
            with st.expander("Evidence and verifier explanations"):
                for item in audit:
                    st.markdown(f"**{item.get('pair_id')} — {item.get('classification')} ({item.get('semantic_score')}/100)**")
                    st.write(item.get("connection_explanation", ""))
                    st.write("A:", item.get("evidence_a", ""))
                    st.write("B:", item.get("evidence_b", ""))
        st.subheader("Three-part hub candidates")
        hubs = selection_data.get("verified_hub_montages", [])
        if not hubs:
            st.info("No multi-edge hub candidates met the duration and evidence constraints.")
        for hub in hubs:
            st.warning(hub.get("connection_explanation", "Editorial review required."))
            st.write("Pair evidence:", ", ".join(hub.get("connection_evidence_pair_ids", [])))
            st.write(hub.get("sequence_explanation", ""))
            st.dataframe(pd.DataFrame([
                {"Order": i, "Episode": s.get("episode"), "Start": s.get("start_time"), "End": s.get("end_time"), "Duration": s.get("duration"), "Anchor event": s.get("anchor_event_id")}
                for i, s in enumerate(hub.get("ordered_segments", []), start=1)
            ]), use_container_width=True, hide_index=True)


# --------------------------------------------------
# PROMO QUALITY REVIEW
# --------------------------------------------------

elif page == "Promo Quality Review":

    st.title("Promo Quality Review")
    baseline_evaluation_data = load_optional_json("promo_evaluation.json")
    expanded_evaluation_data = load_optional_json("expanded/promo_evaluation.json")
    evaluation_data = expanded_evaluation_data or baseline_evaluation_data
    validation_data = load_optional_json("promo_validation_results.json")
    expanded_data = load_optional_json("expanded/promo_validation_results.json")
    if not evaluation_data:
        st.info("No promo evaluation output found. Run the local promo pipeline and evaluator first.")
    else:
        promos = list(evaluation_data.get("evaluated_promos", []))
        ranked_promos = sorted(
            evaluation_data.get("evaluated_promos", []),
            key=lambda item: (item.get("evaluation") or {}).get("overall_score", 0),
            reverse=True,
        )
        st.subheader("Baseline promo ranking")
        st.dataframe(pd.DataFrame([
            {
                "Rank": rank,
                "Promo": item.get("promo_id"),
                "Score": (item.get("evaluation") or {}).get("overall_score"),
                "Decision": (item.get("evaluation") or {}).get("decision"),
                "Episodes": ", ".join(item.get("episodes", [])),
                "Segments": item.get("segment_count"),
                "Duration": item.get("actual_duration", item.get("total_duration")),
                "Pitch": (item.get("evaluation") or {}).get("one_line_pitch", ""),
            }
            for rank, item in enumerate(ranked_promos, start=1)
        ]), use_container_width=True, hide_index=True)
        known_ids = {item.get("promo_id") for item in promos}
        for item in (expanded_data or {}).get("validated_promos", []):
            if item.get("promo_id") not in known_ids:
                promos.append(item)
        if not promos:
            st.info("The evaluation output contains no evaluated promos.")
        else:
            choices = sorted(
                promos,
                key=lambda item: (
                    (item.get("evaluation") or {}).get("overall_score", -1),
                    item.get("promo_id", ""),
                ),
                reverse=True,
            )
            labels = {
                item.get("promo_id", "(missing id)"): item
                for item in choices
            }
            selected_id = st.selectbox(
                "Select promo",
                list(labels),
                format_func=lambda promo_id: (
                    f"{promo_id} | {(labels[promo_id].get('evaluation') or {}).get('overall_score', 'pending evaluation')}"
                ),
            )
            promo = labels[selected_id]
            evaluation = promo.get("evaluation") or {}
            validation_by_id = {
                item.get("promo_id"): item
                for item in (
                    (validation_data or {}).get("validated_promos", [])
                    + (expanded_data or {}).get("validated_promos", [])
                )
            }
            validation = validation_by_id.get(selected_id, promo)
            stats = evaluation_data.get("statistics", {})
            a, b, c = st.columns(3)
            a.metric("Evaluated promos", stats.get("total_evaluated", len(promos)))
            a.metric("Decision", evaluation.get("decision", "evaluation pending").title())
            b.metric("Overall score", evaluation.get("overall_score", "—"))
            c.metric("Duration", f"{promo.get('actual_duration', promo.get('total_duration', '—'))} sec")
            st.caption("Structural validation warnings require editorial review; the evaluator scores are model assessments, not objective verification.")
            st.subheader("Quality scores")
            score_keys = [
                "opening_hook", "standalone_coherence", "narrative_flow",
                "emotional_impact", "cliffhanger_effectiveness", "promotional_appeal",
            ]
            score_frame = pd.DataFrame({
                "Dimension": score_keys,
                "Score": [evaluation.get(key) for key in score_keys],
            }).dropna()
            if not evaluation:
                st.info("This expanded composition has not been sent for model evaluation. Review the source sequence manually before considering it.")
            elif not score_frame.empty:
                st.bar_chart(score_frame.set_index("Dimension"))
            for label, key in [
                ("Hook", "hook_explanation"), ("Standalone coherence", "coherence_explanation"),
                ("Narrative flow", "flow_explanation"), ("Cliffhanger", "cliffhanger_explanation"),
                ("Editorial suggestion", "improvement_suggestion"),
            ]:
                if evaluation.get(key):
                    st.markdown(f"**{label}:** {evaluation[key]}")
            st.subheader("Source sequence")
            st.dataframe(pd.DataFrame([
                {
                    "Order": segment.get("segment_order"),
                    "Episode": segment.get("episode"),
                    "Start": segment.get("start_time"),
                    "End": segment.get("end_time"),
                    "Duration": segment.get("duration"),
                    "Text": segment.get("text", ""),
                }
                for segment in promo.get("segments", [])
            ]), use_container_width=True, hide_index=True)
            warnings = validation.get("validation_warnings", [])
            errors = validation.get("validation_errors", [])
            st.subheader("Structural validation")
            st.write(f"Status: **{validation.get('validation_status', 'unavailable')}**")
            if errors:
                st.error("Hard validation errors")
                st.json(errors)
            if warnings:
                st.warning(f"{len(warnings)} quality warning(s) need review")
                st.dataframe(pd.DataFrame(warnings), use_container_width=True, hide_index=True)
            elif not errors:
                st.success("No structural warnings are recorded for this promo.")
            st.subheader("Manual editorial notes")
            notes = st.text_area(
                "Review notes", key=f"review_notes_{selected_id}",
                placeholder="Record an editorial decision or follow-up note.",
            )
            review_notes = st.session_state.setdefault("promo_review_notes", {})
            if notes:
                review_notes[selected_id] = notes
            st.caption("Notes are kept in this browser session until you download them.")
            if review_notes:
                st.download_button(
                    "Download review notes",
                    data=json.dumps(review_notes, ensure_ascii=False, indent=2),
                    file_name="promo_editorial_review_notes.json",
                    mime="application/json",
                )
