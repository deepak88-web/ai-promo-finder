
import streamlit as st
import pandas as pd
from pathlib import Path


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
        "Candidate Details"
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
