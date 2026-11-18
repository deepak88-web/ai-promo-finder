import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.promo_composer.promo_builder import build_multi_segment_promo
from src.promo_composer.promo_validator import validate_promo

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="AI Promo Finder",
    page_icon="🎬",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_ROOT = PROJECT_ROOT / "outputs"


# --------------------------------------------------
# RUN DISCOVERY & DATA LOADING
# --------------------------------------------------

def discover_available_runs() -> dict[str, Path]:
    """Discover all runs available in the workspace."""
    runs = {}

    # 1. Baseline 50-episode run
    baseline_rep = OUTPUTS_ROOT / "reports"
    if (baseline_rep / "global_ranking.csv").exists():
        runs["Baseline Run (50 Episodes)"] = OUTPUTS_ROOT

    # 2. Expanded run if present
    expanded_dir = OUTPUTS_ROOT / "raw" / "expanded"
    if (expanded_dir / "promo_evaluation.json").exists():
        runs["Expanded Run"] = OUTPUTS_ROOT

    # 3. Dynamic runs in outputs/new_input_runs
    runs_dir = OUTPUTS_ROOT / "new_input_runs"
    if runs_dir.exists():
        for run_path in sorted(runs_dir.iterdir(), reverse=True):
            if run_path.is_dir():
                runs[f"Run: {run_path.name}"] = run_path

    if not runs:
        runs["Default Workspace"] = OUTPUTS_ROOT

    return runs


def load_run_data(run_path: Path, is_expanded: bool = False):
    """Load candidate CSVs safely for the selected run."""
    reports_dir = run_path / "reports" if run_path != OUTPUTS_ROOT else OUTPUTS_ROOT / "reports"

    master_path = reports_dir / "master_candidate_results.csv"
    ranking_path = reports_dir / "global_ranking.csv"
    summary_path = reports_dir / "episode_summary.csv"

    master_df = pd.read_csv(master_path) if master_path.exists() else pd.DataFrame()
    ranking_df = pd.read_csv(ranking_path) if ranking_path.exists() else pd.DataFrame()
    episode_df = pd.read_csv(summary_path) if summary_path.exists() else pd.DataFrame()

    return master_df, ranking_df, episode_df


def load_run_json(run_path: Path, relative_path: str):
    """Load JSON from run raw/final directories."""
    candidates = [
        run_path / relative_path,
        run_path / "raw" / relative_path,
        run_path / "final" / relative_path,
        OUTPUTS_ROOT / "raw" / relative_path,
        OUTPUTS_ROOT / "final" / relative_path,
        OUTPUTS_ROOT / relative_path,
    ]
    for p in candidates:
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return None


def test_provider_connection(provider: str, api_key: str | None, model: str | None = None, base_url: str | None = None):
    """Test connection to the chosen AI provider."""
    from src.llm.provider_router import get_provider

    if provider == "mock":
        return True, "Mock provider is ready (deterministic offline mode)."

    try:
        _, generate_json = get_provider("layer1", provider_override=provider)
        test_sys = "You are a test assistant. Output valid JSON only."
        test_user = "Return a JSON object with key 'status' equal to 'ok'."
        res = generate_json(test_sys, test_user, api_key=api_key, model=model, base_url=base_url)
        if isinstance(res, dict) and (res.get("status") == "ok" or len(res) > 0):
            return True, f"Connection to {provider.title()} successful!"
        return True, f"Response received from {provider.title()}."
    except Exception as exc:
        return False, f"{provider.title()} connection error: {exc}"


def zip_directory_to_bytes(dir_path: Path) -> bytes:
    """Create a zip in memory from a directory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in dir_path.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=file.relative_to(dir_path))
    buf.seek(0)
    return buf.getvalue()


def get_effective_key(provider: str) -> str | None:
    """Retrieve API key strictly from user session in memory; does not read or rely on .env in realtime."""
    if provider == "mock":
        return "mock-key"
    key = st.session_state.get(f"custom_api_key_{provider}", "").strip()
    return key if key else None


# --------------------------------------------------
# SIDEBAR NAVIGATION & SETTINGS
# --------------------------------------------------

st.sidebar.title("🎬 AI Promo Finder")
st.sidebar.caption("Automated Promotional Clip Discovery & Evaluation")

# 1. Run Selection
available_runs = discover_available_runs()
selected_run_name = st.sidebar.selectbox(
    "📁 Select Run Dataset",
    list(available_runs.keys()),
    index=0,
)
current_run_path = available_runs[selected_run_name]
is_expanded_run = "Expanded" in selected_run_name

# Load data for selected run
master_df, ranking_df, episode_df = load_run_data(current_run_path, is_expanded=is_expanded_run)

# --------------------------------------------------
# MODEL & API CONFIGURATION MODAL (POPUP)
# --------------------------------------------------

PROVIDER_PRESET_MODELS = {
    "gemini": ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-2.5-pro", "Custom..."],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama-3.1-70b-versatile", "mixtral-8x7b-32768", "Custom..."],
    "openai_compatible": ["gpt-4o-mini", "gpt-4o", "deepseek-chat", "deepseek-reasoner", "Custom..."],
    "mock": ["mock-model"],
}


@st.dialog("⚙️ Configure AI Engine & API Keys", width="large")
def configure_api_modal():
    st.markdown("### 🔒 Secure Credentials & Engine Setup")
    st.caption(
        "All credentials, models, and per-layer routing rules are kept strictly in this browser tab's session memory. "
        "No `.env` file is required. Nothing is saved to disk, logged, or shared across users."
    )

    tab_quick, tab_advanced, tab_keys = st.tabs([
        "🚀 Unified Engine",
        "🔀 Hybrid / Per-Layer Routing",
        "🔑 Manage API Keys",
    ])

    with tab_quick:
        st.subheader("Unified Provider (Single Engine for All Layers)")
        current_p = st.session_state.get("selected_provider", "gemini")
        provider_options = ["gemini", "groq", "openai_compatible", "mock"]
        p_idx = provider_options.index(current_p) if current_p in provider_options else 0

        chosen_p = st.selectbox(
            "AI Provider",
            provider_options,
            index=p_idx,
            format_func=lambda x: {
                "gemini": "Google Gemini (Recommended: gemini-3.6-flash)",
                "groq": "Groq Cloud (Ultra-Fast: llama-3.3-70b-versatile)",
                "openai_compatible": "OpenAI / vLLM / DeepSeek Compatible",
                "mock": "Offline Mock (Deterministic - No Key Needed)",
            }.get(x, x),
            key="quick_provider_select",
        )

        choices = PROVIDER_PRESET_MODELS.get(chosen_p, ["default"])
        cur_m = st.session_state.get(f"model_{chosen_p}", choices[0])
        m_idx = choices.index(cur_m) if cur_m in choices else 0

        selected_preset = st.selectbox("Select Model", choices, index=m_idx, key=f"quick_model_{chosen_p}")
        if selected_preset == "Custom...":
            final_model = st.text_input("Custom Model ID", value="" if cur_m in choices else cur_m, key=f"quick_custom_{chosen_p}")
        else:
            final_model = selected_preset

        base_url = None
        if chosen_p == "openai_compatible":
            base_url = st.text_input(
                "API Base URL",
                value=st.session_state.get("openai_base_url", "https://api.openai.com/v1"),
                key="quick_base_url",
            )

        st.markdown("---")
        has_key = bool(st.session_state.get(f"custom_api_key_{chosen_p}", "").strip())

        if chosen_p == "mock":
            st.info("ℹ️ Offline Mock Mode: No API key needed.")
            quick_key = ""
        else:
            if has_key:
                st.success(f"🔒 Active {chosen_p.title()} key configured in memory.")
            else:
                st.warning(f"⚠️ No key configured for {chosen_p.title()}.")

            quick_key = st.text_input(
                f"Enter {chosen_p.title()} API Key (Optional if already saved)",
                type="password",
                value="",
                placeholder="Paste key here (e.g. AIzaSy... or gsk_...)",
                key=f"quick_key_{chosen_p}",
            )

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("💾 Apply Unified Engine", type="primary", use_container_width=True, key="btn_apply_quick"):
                st.session_state["routing_mode"] = "unified"
                st.session_state["selected_provider"] = chosen_p
                st.session_state[f"model_{chosen_p}"] = final_model
                if chosen_p == "openai_compatible" and base_url:
                    st.session_state["openai_base_url"] = base_url
                if chosen_p != "mock" and quick_key.strip():
                    st.session_state[f"custom_api_key_{chosen_p}"] = quick_key.strip()
                st.success("Unified configuration saved!")
                st.rerun()

        with c2:
            if st.button("🧪 Test Connection", use_container_width=True, key="btn_test_quick"):
                candidate_k = quick_key.strip() or st.session_state.get(f"custom_api_key_{chosen_p}", "").strip()
                if not candidate_k and chosen_p != "mock":
                    st.error("Please enter a key to test.")
                else:
                    with st.spinner(f"Testing {chosen_p} connection..."):
                        ok, msg = test_provider_connection(chosen_p, candidate_k, model=final_model, base_url=base_url)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

    with tab_advanced:
        st.subheader("Hybrid / Per-Layer Multi-Provider Routing")
        st.caption("Replaces legacy `.env` layer settings (LAYER1_PROVIDER, LAYER2_PROVIDER, PROMO_EVALUATION_PROVIDER).")

        col_l1, col_l2, col_pe = st.columns(3)
        providers = ["gemini", "groq", "openai_compatible", "mock"]

        # Layer 1
        with col_l1:
            st.markdown("#### 1️⃣ Layer 1\n*Dramatic Events*")
            l1_cur_p = st.session_state.get("layer1_provider", "gemini")
            l1_p = st.selectbox("Provider", providers, index=providers.index(l1_cur_p) if l1_cur_p in providers else 0, key="adv_l1_p")
            l1_models = PROVIDER_PRESET_MODELS.get(l1_p, ["default"])
            l1_cur_m = st.session_state.get("layer1_model", l1_models[0])
            l1_m_preset = st.selectbox("Model", l1_models, index=l1_models.index(l1_cur_m) if l1_cur_m in l1_models else 0, key="adv_l1_m")
            l1_m = st.text_input("Custom ID", value="" if l1_cur_m in l1_models else l1_cur_m, key="adv_l1_custom") if l1_m_preset == "Custom..." else l1_m_preset

        # Layer 2
        with col_l2:
            st.markdown("#### 2️⃣ Layer 2\n*Candidate Evaluation*")
            l2_cur_p = st.session_state.get("layer2_provider", "groq")
            l2_p = st.selectbox("Provider", providers, index=providers.index(l2_cur_p) if l2_cur_p in providers else 1, key="adv_l2_p")
            l2_models = PROVIDER_PRESET_MODELS.get(l2_p, ["default"])
            l2_cur_m = st.session_state.get("layer2_model", l2_models[0])
            l2_m_preset = st.selectbox("Model", l2_models, index=l2_models.index(l2_cur_m) if l2_cur_m in l2_models else 0, key="adv_l2_m")
            l2_m = st.text_input("Custom ID", value="" if l2_cur_m in l2_models else l2_cur_m, key="adv_l2_custom") if l2_m_preset == "Custom..." else l2_m_preset

        # Promo Evaluation
        with col_pe:
            st.markdown("#### 3️⃣ Promo Eval\n*Final Quality Scoring*")
            pe_cur_p = st.session_state.get("promo_eval_provider", "gemini")
            pe_p = st.selectbox("Provider", providers, index=providers.index(pe_cur_p) if pe_cur_p in providers else 0, key="adv_pe_p")
            pe_models = PROVIDER_PRESET_MODELS.get(pe_p, ["default"])
            pe_cur_m = st.session_state.get("promo_eval_model", pe_models[0])
            pe_m_preset = st.selectbox("Model", pe_models, index=pe_models.index(pe_cur_m) if pe_cur_m in pe_models else 0, key="adv_pe_m")
            pe_m = st.text_input("Custom ID", value="" if pe_cur_m in pe_models else pe_cur_m, key="adv_pe_custom") if pe_m_preset == "Custom..." else pe_m_preset

        st.markdown("---")
        if st.button("🔀 Apply Hybrid / Per-Layer Routing", type="primary", use_container_width=True, key="btn_apply_adv"):
            st.session_state["routing_mode"] = "per_layer"
            st.session_state["layer1_provider"] = l1_p
            st.session_state["layer1_model"] = l1_m
            st.session_state["layer2_provider"] = l2_p
            st.session_state["layer2_model"] = l2_m
            st.session_state["promo_eval_provider"] = pe_p
            st.session_state["promo_eval_model"] = pe_m
            st.success("Hybrid routing activated!")
            st.rerun()

    with tab_keys:
        st.subheader("In-Memory API Key Management")
        st.caption("Enter credentials for the providers you use. Keys are never rendered in plain text.")

        # Gemini
        st.markdown("#### 🌟 Google Gemini")
        has_gemini = bool(st.session_state.get("custom_api_key_gemini", "").strip())
        if has_gemini:
            st.success("🔒 Gemini Key Active in Memory")
        else:
            st.warning("⚠️ No Gemini Key Entered")
        gk_input = st.text_input("Gemini API Key", type="password", value="", placeholder="AIzaSy...", key="key_tab_gemini")
        g_c1, g_c2, g_c3 = st.columns([1, 1, 1])
        if g_c1.button("Save Gemini Key", key="save_gemini"):
            if gk_input.strip():
                st.session_state["custom_api_key_gemini"] = gk_input.strip()
                st.rerun()
        if g_c2.button("Test Gemini", key="test_gemini"):
            cand = gk_input.strip() or st.session_state.get("custom_api_key_gemini", "")
            if cand:
                ok, msg = test_provider_connection("gemini", cand, model=st.session_state.get("model_gemini", "gemini-3.6-flash"))
                st.success(msg) if ok else st.error(msg)
            else:
                st.error("No Gemini key to test.")
        if has_gemini and g_c3.button("Clear Gemini Key", key="clear_gemini"):
            st.session_state["custom_api_key_gemini"] = ""
            st.rerun()

        st.markdown("---")

        # Groq
        st.markdown("#### ⚡ Groq Cloud")
        has_groq = bool(st.session_state.get("custom_api_key_groq", "").strip())
        if has_groq:
            st.success("🔒 Groq Key Active in Memory")
        else:
            st.warning("⚠️ No Groq Key Entered")
        grk_input = st.text_input("Groq API Key", type="password", value="", placeholder="gsk_...", key="key_tab_groq")
        gr_c1, gr_c2, gr_c3 = st.columns([1, 1, 1])
        if gr_c1.button("Save Groq Key", key="save_groq"):
            if grk_input.strip():
                st.session_state["custom_api_key_groq"] = grk_input.strip()
                st.rerun()
        if gr_c2.button("Test Groq", key="test_groq"):
            cand = grk_input.strip() or st.session_state.get("custom_api_key_groq", "")
            if cand:
                ok, msg = test_provider_connection("groq", cand, model=st.session_state.get("model_groq", "llama-3.3-70b-versatile"))
                st.success(msg) if ok else st.error(msg)
            else:
                st.error("No Groq key to test.")
        if has_groq and gr_c3.button("Clear Groq Key", key="clear_groq"):
            st.session_state["custom_api_key_groq"] = ""
            st.rerun()

        st.markdown("---")

        # OpenAI / Custom Base URL
        st.markdown("#### 🌐 OpenAI / vLLM / DeepSeek")
        has_oai = bool(st.session_state.get("custom_api_key_openai_compatible", "").strip())
        if has_oai:
            st.success("🔒 OpenAI-Compatible Key Active in Memory")
        oai_url = st.text_input("Base URL", value=st.session_state.get("openai_base_url", "https://api.openai.com/v1"), key="key_tab_oai_url")
        oai_input = st.text_input("API Key", type="password", value="", placeholder="sk-...", key="key_tab_oai_key")
        o_c1, o_c2, o_c3 = st.columns([1, 1, 1])
        if o_c1.button("Save OpenAI Key", key="save_oai"):
            st.session_state["openai_base_url"] = oai_url
            if oai_input.strip():
                st.session_state["custom_api_key_openai_compatible"] = oai_input.strip()
                st.rerun()
        if o_c2.button("Test OpenAI", key="test_oai"):
            cand = oai_input.strip() or st.session_state.get("custom_api_key_openai_compatible", "")
            ok, msg = test_provider_connection("openai_compatible", cand, model=st.session_state.get("model_openai_compatible", "gpt-4o-mini"), base_url=oai_url)
            st.success(msg) if ok else st.error(msg)
        if has_oai and o_c3.button("Clear OpenAI Key", key="clear_oai"):
            st.session_state["custom_api_key_openai_compatible"] = ""
            st.rerun()


# 2. Engine & Model Status in Sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ AI Engine Settings")

routing_mode = st.session_state.get("routing_mode", "unified")

if routing_mode == "per_layer":
    l1_p = st.session_state.get("layer1_provider", "gemini")
    l1_m = st.session_state.get("layer1_model", "gemini-3.6-flash")
    l2_p = st.session_state.get("layer2_provider", "groq")
    l2_m = st.session_state.get("layer2_model", "llama-3.3-70b-versatile")
    pe_p = st.session_state.get("promo_eval_provider", "gemini")
    pe_m = st.session_state.get("promo_eval_model", "gemini-3.6-flash")

    st.sidebar.info(
        f"**🔀 Hybrid Routing Active**\n\n"
        f"• **L1**: {l1_p.title()} (`{l1_m}`)\n\n"
        f"• **L2**: {l2_p.title()} (`{l2_m}`)\n\n"
        f"• **Promo**: {pe_p.title()} (`{pe_m}`)"
    )
else:
    chosen_provider = st.session_state.get("selected_provider", "gemini")
    default_models = {
        "gemini": "gemini-3.6-flash",
        "groq": "llama-3.3-70b-versatile",
        "openai_compatible": "gpt-4o-mini",
        "mock": "mock-model",
    }
    session_model = st.session_state.get(f"model_{chosen_provider}", default_models.get(chosen_provider, "default"))
    effective_key = get_effective_key(chosen_provider)
    has_key = bool(effective_key)

    if chosen_provider == "mock":
        st.sidebar.info(f"**Provider**: Mock (Offline)\n\n**Model**: `{session_model}`")
    elif has_key:
        st.sidebar.success(f"**Provider**: {chosen_provider.title()}\n\n**Model**: `{session_model}`\n\n🔒 **Key Active** (In Memory)")
    else:
        st.sidebar.warning(f"**Provider**: {chosen_provider.title()}\n\n**Model**: `{session_model}`\n\n⚠️ **No Key Set**")

if st.sidebar.button("⚙️ Configure Engine & Keys", use_container_width=True, type="primary"):
    configure_api_modal()

st.sidebar.divider()

# Navigation Radio
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Global Rankings",
        "Episode Explorer",
        "Candidate Details",
        "Candidate Comparison",
        "Promo Quality Review",
        "Promo Composer",
        "Cross-Episode Discovery",
        "New Input Processing",
    ],
)


# Alert banner if no key is configured and provider requires one
if chosen_provider != "mock" and not has_key:
    c_warn, c_btn = st.columns([3, 1])
    with c_warn:
        st.warning("⚠️ **No API Key Configured in Session**: Running in report-browsing mode. To run live AI pipeline tasks, open the popup to configure your API key or switch to Mock mode.")
    with c_btn:
        if st.button("⚙️ Configure API Key", key="banner_config_btn", type="primary"):
            configure_api_modal()

st.divider()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":
    st.title("AI Promo Finder Dashboard")
    st.write("Discover the most engaging promotional moments across screenplay episodes.")

    if ranking_df.empty:
        st.info(
            "No candidate rankings found for this run. "
            "Go to **New Input Processing** to run on sample data or upload a screenplay pack."
        )
        if st.button("Go to New Input Processing"):
            st.switch_page = "New Input Processing"
    else:
        total_episodes = episode_df["episode"].nunique() if not episode_df.empty else 0
        total_candidates = len(master_df)
        evaluated_candidates = master_df["weighted_score"].notna().sum() if "weighted_score" in master_df.columns else 0
        average_score = master_df["weighted_score"].mean() if "weighted_score" in master_df.columns else 0.0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Episodes Processed", total_episodes)
        col2.metric("Total Candidates", total_candidates)
        col3.metric("Evaluated Candidates", evaluated_candidates)
        col4.metric("Average Score", f"{average_score:.2f}/10")

        st.divider()

        best_candidate = ranking_df.iloc[0]
        st.subheader("🏆 Best Promotional Candidate")

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"### {best_candidate['candidate_id']}")
            st.write(f"Episode: **{best_candidate['episode']}**")
            st.write(f"Weighted Score: **{best_candidate['weighted_score']}/10**")
            if "duration" in best_candidate:
                st.write(f"Duration: **{best_candidate['duration']} seconds**")
        with c2:
            st.metric("Top Candidate Score", f"{best_candidate['weighted_score']}/10")

        st.divider()

        st.subheader("Top 10 Promotional Candidates")
        display_cols = [c for c in ["global_rank", "episode", "candidate_id", "duration", "weighted_score"] if c in ranking_df.columns]
        st.dataframe(ranking_df[display_cols].head(10), use_container_width=True, hide_index=True)

        if "candidate_id" in ranking_df.columns and "weighted_score" in ranking_df.columns:
            st.subheader("Candidate Score Distribution")
            st.bar_chart(ranking_df.head(25).set_index("candidate_id")["weighted_score"], height=300)


# --------------------------------------------------
# GLOBAL RANKINGS
# --------------------------------------------------

elif page == "Global Rankings":
    st.title("Global Candidate Rankings")

    if ranking_df.empty:
        st.info("No candidates available for this run. Process a screenplay pack first.")
    else:
        min_score = st.slider("Minimum weighted score", 0.0, 10.0, 0.0, step=0.25)
        episodes_list = ["All Episodes"] + sorted(ranking_df["episode"].unique().tolist()) if "episode" in ranking_df.columns else ["All Episodes"]
        selected_episode = st.selectbox("Filter by episode", episodes_list)

        filtered_df = ranking_df[ranking_df["weighted_score"] >= min_score]
        if selected_episode != "All Episodes":
            filtered_df = filtered_df[filtered_df["episode"] == selected_episode]

        st.write(f"Showing **{len(filtered_df)} candidates**")

        display_columns = [
            c for c in [
                "global_rank", "episode", "candidate_id", "scene_number",
                "start_time", "end_time", "duration", "weighted_score",
            ] if c in filtered_df.columns
        ]

        st.dataframe(filtered_df[display_columns], use_container_width=True, hide_index=True)

        st.download_button(
            "Download Filtered Rankings (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="filtered_global_ranking.csv",
            mime="text/csv",
        )


# --------------------------------------------------
# EPISODE EXPLORER
# --------------------------------------------------

elif page == "Episode Explorer":
    st.title("Episode Explorer")

    if master_df.empty or "episode" not in master_df.columns:
        st.info("No episode candidate data available.")
    else:
        selected_episode = st.selectbox("Select Episode", sorted(master_df["episode"].unique()))
        episode_candidates = master_df[master_df["episode"] == selected_episode].sort_values(
            "weighted_score", ascending=False
        )

        st.subheader(f"Results for {selected_episode}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Candidates", len(episode_candidates))
        best_score = episode_candidates["weighted_score"].max() if not episode_candidates.empty else 0.0
        col2.metric("Best Score", f"{best_score:.2f}")
        if not episode_candidates.empty:
            best_id = episode_candidates.iloc[0]["candidate_id"]
            col3.metric("Best Candidate", best_id)

        st.divider()

        disp_cols = [
            c for c in [
                "candidate_id", "scene_number", "start_time", "end_time",
                "duration", "event_categories", "weighted_score",
            ] if c in episode_candidates.columns
        ]
        st.dataframe(episode_candidates[disp_cols], use_container_width=True, hide_index=True)

        st.subheader("Candidate Descriptions")
        for _, cand in episode_candidates.iterrows():
            with st.expander(f"{cand['candidate_id']} — Score: {cand.get('weighted_score', 'N/A')}"):
                st.write(f"**Duration:** {cand.get('duration')} seconds")
                st.write(f"**Time:** {cand.get('start_time')} – {cand.get('end_time')} seconds")
                st.write(f"**Categories:** {cand.get('event_categories')}")
                st.write("**Description:**")
                st.write(cand.get("descriptions", ""))


# --------------------------------------------------
# CANDIDATE DETAILS
# --------------------------------------------------

elif page == "Candidate Details":
    st.title("Candidate Evaluation Details")

    if ranking_df.empty or "candidate_id" not in ranking_df.columns:
        st.info("No candidates available.")
    else:
        selected_candidate = st.selectbox("Select Candidate", ranking_df["candidate_id"].tolist())
        candidate_rows = master_df[master_df["candidate_id"] == selected_candidate]
        if candidate_rows.empty:
            st.warning("Candidate details not found.")
        else:
            candidate = candidate_rows.iloc[0]
            st.subheader(selected_candidate)

            col1, col2, col3 = st.columns(3)
            col1.metric("Episode", candidate.get("episode", ""))
            col2.metric("Duration", f"{candidate.get('duration')} sec")
            col3.metric("Weighted Score", f"{candidate.get('weighted_score')}/10")

            st.divider()

            score_fields = [
                f for f in [
                    "opening_hook", "emotional_impact", "suspense_curiosity",
                    "narrative_coherence", "promotional_value", "ending_strength",
                ] if f in candidate
            ]
            if score_fields:
                st.subheader("Evaluation Scores")
                score_data = pd.DataFrame({
                    "Evaluation Criteria": score_fields,
                    "Score": [candidate[f] for f in score_fields],
                })
                st.bar_chart(score_data.set_index("Evaluation Criteria"))

            st.divider()
            st.subheader("Candidate Description")
            st.write(candidate.get("descriptions", ""))
            st.subheader("Strengths")
            st.write(candidate.get("strengths", ""))
            st.subheader("Weaknesses")
            st.write(candidate.get("weaknesses", ""))
            st.subheader("Overall Assessment")
            st.info(candidate.get("overall_assessment", ""))


# --------------------------------------------------
# CANDIDATE COMPARISON
# --------------------------------------------------

elif page == "Candidate Comparison":
    st.title("Candidate Comparison")

    if ranking_df.empty or len(ranking_df) < 2:
        st.info("At least two ranked candidates are required for comparison.")
    else:
        candidate_ids = ranking_df["candidate_id"].dropna().astype(str).tolist()
        left, right = st.columns(2)
        first_id = left.selectbox("First candidate", candidate_ids, index=0)
        second_default = 1 if candidate_ids[0] == first_id else 0
        second_id = right.selectbox("Second candidate", candidate_ids, index=second_default, key="comparison_two")

        if first_id == second_id:
            st.warning("Choose two different candidates to compare.")
        else:
            selected = master_df[
                master_df["candidate_id"].astype(str).isin([first_id, second_id])
            ].set_index("candidate_id").loc[[first_id, second_id]]

            score_fields = [
                f for f in [
                    "opening_hook", "emotional_impact", "suspense_curiosity",
                    "narrative_coherence", "promotional_value", "ending_strength",
                    "weighted_score",
                ] if f in selected.columns
            ]
            st.subheader("Scores Comparison")
            st.dataframe(selected[score_fields].T, use_container_width=True)


# --------------------------------------------------
# PROMO QUALITY REVIEW
# --------------------------------------------------

elif page == "Promo Quality Review":
    st.title("Promo Quality Review & Ranked Promos")
    st.caption("Review complete evaluated promotional clips, hook/cliffhanger grounding, and editorial assessments.")

    # Try loading final_promos.json or promo_evaluation.json
    final_promos_data = load_run_json(current_run_path, "final_promos.json")
    evaluation_data = load_run_json(current_run_path, "promo_evaluation.json")
    ranked_promos_json = load_run_json(current_run_path, "ranked_promos.json")

    promos = []
    if final_promos_data and isinstance(final_promos_data, list):
        promos = final_promos_data
    elif ranked_promos_json and "ranked_promos" in ranked_promos_json:
        promos = ranked_promos_json["ranked_promos"]
    elif evaluation_data and "evaluated_promos" in evaluation_data:
        promos = evaluation_data["evaluated_promos"]

    if not promos:
        st.info("No evaluated promos found for this run. Run the pipeline with evaluation enabled in **New Input Processing**.")
    else:
        # Download buttons section
        st.subheader("📥 Export Final Deliverables")
        dcol1, dcol2, dcol3, dcol4 = st.columns(4)

        # Build CSV on the fly if needed
        csv_rows = []
        for p in promos:
            segs = p.get("segments", [])
            segs_str = "; ".join(f"[{s.get('episode')}] {s.get('start_time')}-{s.get('end_time')} ({s.get('duration')}s)" for s in segs)
            hk = p.get("hook", {})
            cl = p.get("cliffhanger", {})
            csv_rows.append({
                "rank": p.get("rank") or p.get("global_rank"),
                "promo_id": p.get("promo_id"),
                "episodes": ", ".join(p.get("episodes", [])),
                "total_duration": p.get("total_duration") or p.get("actual_duration"),
                "segment_count": len(segs),
                "segments": segs_str,
                "hook_summary": hk.get("evidence_text") or hk.get("type", ""),
                "cliffhanger_summary": cl.get("evidence_text") or cl.get("type", ""),
                "one_line_pitch": p.get("one_line_pitch") or p.get("pitch", ""),
                "overall_score": p.get("overall_score") or (p.get("evaluation") or {}).get("overall_score"),
                "decision": p.get("decision") or (p.get("evaluation") or {}).get("decision"),
                "ranking_reason": p.get("ranking_reason", ""),
                "warnings": "; ".join(p.get("warnings", [])),
            })
        final_csv_bytes = pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8")
        final_json_bytes = json.dumps(promos, ensure_ascii=False, indent=2).encode("utf-8")

        dcol1.download_button("Download final_promos.csv", data=final_csv_bytes, file_name="final_promos.csv", mime="text/csv")
        dcol2.download_button("Download final_promos.json", data=final_json_bytes, file_name="final_promos.json", mime="application/json")

        st.divider()

        # Summary statistics
        recommended_count = sum(1 for p in promos if (p.get("decision") or (p.get("evaluation") or {}).get("decision")) == "recommend")
        revision_count = sum(1 for p in promos if (p.get("decision") or (p.get("evaluation") or {}).get("decision")) == "revise")
        rejected_count = sum(1 for p in promos if (p.get("decision") or (p.get("evaluation") or {}).get("decision")) == "reject")

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Promos", len(promos))
        sc2.metric("Recommended (Score ≥ 7.0)", recommended_count)
        sc3.metric("Needs Revision (5.0–6.9)", revision_count)
        sc4.metric("Rejected (Score < 5.0)", rejected_count)

        # Overview Table
        st.subheader("Ranked Promo List")
        table_rows = []
        for idx, p in enumerate(promos, start=1):
            eval_dict = p.get("evaluation") or {}
            score = p.get("overall_score") or eval_dict.get("overall_score")
            decision = p.get("decision") or eval_dict.get("decision")
            table_rows.append({
                "Rank": p.get("rank") or p.get("global_rank") or idx,
                "Promo ID": p.get("promo_id"),
                "Score": f"{score:.2f}" if isinstance(score, (int, float)) else "—",
                "Decision": str(decision).upper() if decision else "PENDING",
                "Duration": f"{p.get('total_duration') or p.get('actual_duration')}s",
                "Episodes": ", ".join(p.get("episodes", [])),
                "Pitch": p.get("one_line_pitch") or eval_dict.get("one_line_pitch", ""),
                "Warnings": len(p.get("warnings", p.get("validation_warnings", []))),
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        st.divider()

        # Detailed Promo Inspector
        st.subheader("🔍 Inspect Single Promo")
        promo_options = {p.get("promo_id", f"Promo {i}"): p for i, p in enumerate(promos)}
        selected_promo_id = st.selectbox("Choose promo to inspect", list(promo_options.keys()))
        selected_promo = promo_options[selected_promo_id]

        ev = selected_promo.get("evaluation") or selected_promo

        pcol1, pcol2, pcol3 = st.columns(3)
        ov_score = selected_promo.get("overall_score") or ev.get("overall_score")
        dec = selected_promo.get("decision") or ev.get("decision")
        dur = selected_promo.get("total_duration") or selected_promo.get("actual_duration")

        pcol1.metric("Overall Score", f"{ov_score}/10" if ov_score else "N/A")
        pcol2.metric("Editorial Decision", str(dec).upper())
        pcol3.metric("Actual Duration", f"{dur}s (20-60s window)")

        st.markdown(f"**One-Line Pitch:** *{ev.get('one_line_pitch', selected_promo.get('one_line_pitch', ''))}*")

        # 6 dimensions
        dim_keys = [
            "opening_hook", "standalone_coherence", "narrative_flow",
            "emotional_impact", "cliffhanger_effectiveness", "promotional_appeal",
        ]
        dim_scores = selected_promo.get("dimension_scores") or {k: ev.get(k) for k in dim_keys if k in ev}
        if dim_scores:
            dim_df = pd.DataFrame([{"Dimension": k.replace("_", " ").title(), "Score": dim_scores.get(k)} for k in dim_keys if k in dim_scores]).dropna()
            if not dim_df.empty:
                st.bar_chart(dim_df.set_index("Dimension"))

        # Screenplay segments
        st.subheader("Screenplay Segments & Timestamps")
        seg_data = []
        for s in selected_promo.get("segments", []):
            seg_data.append({
                "Order": s.get("segment_order"),
                "Episode": s.get("episode"),
                "Start": s.get("start_time"),
                "End": s.get("end_time"),
                "Duration": f"{s.get('duration')}s",
                "Dialogue / Excerpt": s.get("text") or s.get("dialogue_excerpt", ""),
            })
        if seg_data:
            st.dataframe(pd.DataFrame(seg_data), use_container_width=True, hide_index=True)

        # Hook & Cliffhanger
        hk_data = selected_promo.get("hook", {})
        cl_data = selected_promo.get("cliffhanger", {})
        hcol, ccol = st.columns(2)
        with hcol:
            st.markdown("##### 🪝 Opening Hook Grounding")
            st.write(f"**Event ID:** `{hk_data.get('evidence_event_id', 'N/A')}`")
            st.write(f"**Text:** {hk_data.get('evidence_text', 'N/A')}")
            st.write(f"**Explanation:** {ev.get('hook_explanation', '')}")
        with ccol:
            st.markdown("##### ⚡ Ending Cliffhanger Grounding")
            st.write(f"**Event ID:** `{cl_data.get('evidence_event_id', 'N/A')}`")
            st.write(f"**Text:** {cl_data.get('evidence_text', 'N/A')}")
            st.write(f"**Explanation:** {ev.get('cliffhanger_explanation', '')}")

        # Editorial Notes
        st.subheader("Manual Editorial Review Notes")
        note_key = f"review_note_{selected_promo_id}"
        notes = st.text_area(
            "Editorial feedback / director instructions",
            value=st.session_state.get(note_key, ""),
            key=note_key,
        )


# --------------------------------------------------
# PROMO COMPOSER
# --------------------------------------------------

elif page == "Promo Composer":
    st.title("Multi-Segment Promo Composer")
    st.caption("Review a generated composition, adjust its order, and download a timestamped JSON draft.")

    selection_data = load_run_json(current_run_path, "promo_segment_selection.json")
    if not selection_data:
        st.info("No promo segment selection found for this run.")
    else:
        combo_groups = {
            "Same-episode montages": selection_data.get("same_episode_combinations", []),
            "Cross-episode combinations": selection_data.get("cross_episode_combinations", []),
            "Verified hub montages": selection_data.get("verified_hub_montages", []),
        }
        options = []
        indexed = {}
        for g_name, group in combo_groups.items():
            for combo in group:
                key = f"{g_name} | {combo.get('combination_id')}"
                options.append(key)
                indexed[key] = combo

        if not options:
            st.info("No composition candidates available in this run.")
        else:
            chosen_key = st.selectbox("Composition candidate", options)
            combo = indexed[chosen_key]
            source_segments = combo.get("ordered_segments", [])
            st.write(combo.get("connection_explanation", ""))

            st.write(f"Source duration: **{combo.get('combined_source_duration')} seconds** across **{len(source_segments)} segments**")

            # Order selector
            positions = []
            for index, segment in enumerate(source_segments, start=1):
                positions.append(
                    st.selectbox(
                        f"Position for {segment.get('segment_id') or segment.get('candidate_id')} ({segment.get('episode')})",
                        list(range(1, len(source_segments) + 1)),
                        index=index - 1,
                        key=f"composer_pos_{combo.get('combination_id')}_{index}",
                    )
                )

            if len(set(positions)) == len(positions):
                ordered = [seg for _, seg in sorted(zip(positions, source_segments), key=lambda x: x[0])]
                draft_combo = dict(combo)
                draft_combo["ordered_segments"] = ordered
                draft = build_multi_segment_promo(draft_combo)
                if draft:
                    checked = validate_promo(draft)
                    st.subheader("Promo Preview")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Duration", f"{checked.get('actual_duration')} sec")
                    col2.metric("Segments", checked.get("segment_count"))
                    col3.metric("Structural Status", checked.get("validation_status"))

                    st.download_button(
                        "Download Promo Draft JSON",
                        data=json.dumps(checked, ensure_ascii=False, indent=2),
                        file_name=f"{checked['promo_id']}_draft.json",
                        mime="application/json",
                    )


# --------------------------------------------------
# CROSS-EPISODE DISCOVERY
# --------------------------------------------------

elif page == "Cross-Episode Discovery":
    st.title("Cross-Episode Discovery")
    st.caption("Connections are grounded in verified dramatic evidence pairs.")

    selection_data = load_run_json(current_run_path, "promo_segment_selection.json")
    if not selection_data:
        st.info("No cross-episode selection data available for this run.")
    else:
        audit = selection_data.get("verified_pair_audit", [])
        if audit:
            st.metric("Frozen V4 pairs inspected", len(audit))
            audit_rows = [{
                "Pair": item.get("pair_id"),
                "Episodes": f"{item.get('event_a_episode')} → {item.get('event_b_episode')}",
                "Class": item.get("classification"),
                "Score": item.get("semantic_score"),
                "Connection": item.get("connection_mode"),
            } for item in audit]
            st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No cross-episode pairs are recorded for this run.")


# --------------------------------------------------
# NEW INPUT PROCESSING
# --------------------------------------------------

elif page == "New Input Processing":
    st.title("Process a New Screenplay Pack")
    st.write("Upload a ZIP pack or one or more TXT screenplays, or test instantly on the bundled sample pack.")

    routing_mode = st.session_state.get("routing_mode", "unified")
    base_url_for_run = st.session_state.get("openai_base_url")

    if routing_mode == "per_layer":
        l1_p = st.session_state.get("layer1_provider", "gemini")
        l1_m = st.session_state.get("layer1_model", "gemini-3.6-flash")
        l1_k = get_effective_key(l1_p)

        l2_p = st.session_state.get("layer2_provider", "groq")
        l2_m = st.session_state.get("layer2_model", "llama-3.3-70b-versatile")
        l2_k = get_effective_key(l2_p)

        pe_p = st.session_state.get("promo_eval_provider", "gemini")
        pe_m = st.session_state.get("promo_eval_model", "gemini-3.6-flash")
        pe_k = get_effective_key(pe_p)

        st.info(
            f"**Execution Mode: Hybrid Multi-Provider** | "
            f"L1: **{l1_p.title()}** (`{l1_m}`) | "
            f"L2: **{l2_p.title()}** (`{l2_m}`) | "
            f"Promo: **{pe_p.title()}** (`{pe_m}`)"
        )
        missing_keys = [
            f"{stg} ({prv.title()})"
            for stg, prv, ky in [("Layer 1", l1_p, l1_k), ("Layer 2", l2_p, l2_k), ("Promo Eval", pe_p, pe_k)]
            if prv != "mock" and not ky
        ]
        has_required_keys = len(missing_keys) == 0
        missing_msg = f"Missing key for: {', '.join(missing_keys)}" if missing_keys else ""
    else:
        chosen_p = st.session_state.get("selected_provider", "gemini")
        m_for_run = st.session_state.get(f"model_{chosen_p}", "gemini-3.6-flash")
        k_for_run = get_effective_key(chosen_p)

        l1_p = l2_p = pe_p = chosen_p
        l1_m = l2_m = pe_m = m_for_run
        l1_k = l2_k = pe_k = k_for_run

        st.info(f"**Execution Mode: Unified** | Provider: **{chosen_p.title()}** | Model: **{m_for_run}**")
        has_required_keys = (chosen_p == "mock") or bool(k_for_run)
        missing_msg = f"No API key configured for {chosen_p.title()}."

    # Mode tabs: 1. Sample Pack test, 2. Custom Upload
    tab_sample, tab_upload = st.tabs(["🚀 One-Click Sample Test", "📁 Upload Custom Pack"])

    with tab_sample:
        st.subheader("Instant Test on Bundled Sample Pack")
        st.write("Runs the complete end-to-end pipeline on `sample_data/sample_screenplays.zip` (2 episodes).")

        eval_sample = st.checkbox("Run promo-level LLM evaluation on sample", value=True, key="eval_sample")

        if not has_required_keys:
            st.warning(f"⚠️ {missing_msg} Configure your credentials via the popup or switch to Mock offline mode.")
            if st.button("⚙️ Open Model & API Key Popup", key="btn_sample_config"):
                configure_api_modal()
        elif st.button("Run Pipeline on Sample Pack", type="primary"):
            sample_zip = PROJECT_ROOT / "sample_data" / "sample_screenplays.zip"
            if not sample_zip.exists():
                st.error(f"Sample file not found at {sample_zip}")
            else:
                run_id = datetime.now().strftime("sample_run_%Y%m%d_%H%M%S")
                out_dir = OUTPUTS_ROOT / "new_input_runs" / run_id

                from src.pipeline.run_new_input_pack import run as run_pack
                with st.spinner(f"Running pipeline on sample screenplays..."):
                    try:
                        res = run_pack(
                            sample_zip,
                            out_dir,
                            evaluate=eval_sample,
                            provider=l1_p,
                            model=l1_m,
                            api_key=l1_k,
                            base_url=base_url_for_run,
                            layer1_provider=l1_p,
                            layer1_model=l1_m,
                            layer1_key=l1_k,
                            layer2_provider=l2_p,
                            layer2_model=l2_m,
                            layer2_key=l2_k,
                            promo_eval_provider=pe_p,
                            promo_eval_model=pe_m,
                            promo_eval_key=pe_k,
                        )
                        st.success(f"Run completed successfully! Outputs saved to `{out_dir.name}`")
                        st.json(res)

                        # Provide instant download buttons
                        final_json = out_dir / "final" / "final_promos.json"
                        final_csv = out_dir / "final" / "final_promos.csv"
                        c1, c2, c3 = st.columns(3)
                        if final_csv.exists():
                            c1.download_button("Download final_promos.csv", final_csv.read_bytes(), "final_promos.csv", "text/csv")
                        if final_json.exists():
                            c2.download_button("Download final_promos.json", final_json.read_bytes(), "final_promos.json", "application/json")
                        c3.download_button("Download Entire Run ZIP", zip_directory_to_bytes(out_dir), f"{run_id}.zip", "application/zip")

                    except Exception as err:
                        st.error(f"Run failed: {err}")

    with tab_upload:
        st.subheader("Upload Custom Screenplays")
        uploads = st.file_uploader(
            "Upload Screenplay ZIP or TXT files",
            type=["zip", "txt"],
            accept_multiple_files=True,
        )
        eval_custom = st.checkbox("Run promo-level LLM evaluation", value=True, key="eval_custom")

        if not has_required_keys:
            st.warning(f"⚠️ {missing_msg} Configure your credentials via the popup or switch to Mock offline mode.")
            if st.button("⚙️ Open Model & API Key Popup", key="btn_custom_config"):
                configure_api_modal()
        elif st.button("Process Uploaded Screenplays", disabled=not uploads, type="primary"):
            with tempfile.TemporaryDirectory(prefix="promo_upload_") as tmp_dir:
                tmp_dir_path = Path(tmp_dir)
                if len(uploads) == 1 and uploads[0].name.lower().endswith(".zip"):
                    input_target = tmp_dir_path / uploads[0].name
                    input_target.write_bytes(uploads[0].getvalue())
                else:
                    input_target = tmp_dir_path / "screenplays"
                    input_target.mkdir()
                    for up in uploads:
                        (input_target / Path(up.name).name).write_bytes(up.getvalue())

                run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
                out_dir = OUTPUTS_ROOT / "new_input_runs" / run_id

                from src.pipeline.run_new_input_pack import run as run_pack
                with st.spinner("Processing screenplay pack..."):
                    try:
                        res = run_pack(
                            input_target,
                            out_dir,
                            evaluate=eval_custom,
                            provider=l1_p,
                            model=l1_m,
                            api_key=l1_k,
                            base_url=base_url_for_run,
                            layer1_provider=l1_p,
                            layer1_model=l1_m,
                            layer1_key=l1_k,
                            layer2_provider=l2_p,
                            layer2_model=l2_m,
                            layer2_key=l2_k,
                            promo_eval_provider=pe_p,
                            promo_eval_model=pe_m,
                            promo_eval_key=pe_k,
                        )
                        st.success(f"Processing finished! Output saved to `{out_dir.name}`")
                        st.json(res)

                        final_json = out_dir / "final" / "final_promos.json"
                        final_csv = out_dir / "final" / "final_promos.csv"
                        c1, c2, c3 = st.columns(3)
                        if final_csv.exists():
                            c1.download_button("Download final_promos.csv", final_csv.read_bytes(), "final_promos.csv", "text/csv")
                        if final_json.exists():
                            c2.download_button("Download final_promos.json", final_json.read_bytes(), "final_promos.json", "application/json")
                        c3.download_button("Download Run ZIP", zip_directory_to_bytes(out_dir), f"{run_id}.zip", "application/zip")

                    except Exception as err:
                        st.error(f"Processing stopped with error: {err}")
