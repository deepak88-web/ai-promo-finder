# AI Promo Finder

An end-to-end, production-ready AI application for Kuku's assignment **Problem 1: Find the Promos**. It ingests timestamped screenplay packs, identifies dramatic turning points, ranks candidate moments, composes verified 20–60 second promos with exact timestamp tracking, grounds opening hooks and ending cliffhangers, and provides an interactive Streamlit review interface.

---

## ⚡ Quickstart with Docker

Run the entire application in a container with a single command:

```bash
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) in your browser.
- All generated reports, final promo exports, and new runs persist in `./outputs` on your host machine.
- API keys can be passed via `.env` or entered interactively directly in the UI sidebar.

---

## 💻 Local Setup & Execution

### 1. Installation

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Launch the Streamlit Interface

```bash
streamlit run app.py
```

- **Interactive Key & Model Management**: Expand **Model & API Settings** in the sidebar. Choose your provider (`Gemini`, `Groq`, `OpenAI Compatible`, or `Mock (Offline)`), paste your key, test the connection with 1 click, and run without ever editing `.env` or writing keys to disk.
- **One-Click Sample Run**: Go to **New Input Processing** -> click **"Run Pipeline on Sample Pack"** to execute the complete pipeline on the bundled 2-episode screenplay pack in seconds.
- **Direct Exports**: Download `final_promos.csv`, `final_promos.json`, and run archive ZIP files directly from the UI.

---

## 🧪 Deterministic Offline Tests

Run the complete offline test suite (zero network calls, zero API keys required):

```bash
pytest -v
```

All 13 unit tests verify:
- Screenplay parsing across flexible timestamp formats (`MM:SS.hh`, `HH:MM:SS`, `MM:SS`, floats, and fallback scene bounds).
- Candidate window generation with verbatim dialogue excerpt extraction.
- Layer 2 dialogue awareness.
- Provider router fallback (`Gemini`, `Groq`, `OpenAI-compatible`, and `Mock`).
- Deterministic promo evaluation scoring and decision thresholds.
- Strict 20–60 second promo duration validation and hook/cliffhanger grounding.
- Unified assignment exports (`final_promos.json` and `final_promos.csv`).
- Complete pipeline execution on sample data with mock provider.

---

## 📦 Running on New Screenplay Packs (CLI)

Run the full automated pipeline on any ZIP archive, directory of TXT scripts, or single screenplay file:

```bash
# Offline dry-run with mock provider:
python -m src.pipeline.run_new_input_pack --input sample_data/sample_screenplays.zip --output-dir outputs/new_input_runs/test_run --evaluate --provider mock

# Live run with Gemini:
python -m src.pipeline.run_new_input_pack --input path/to/screenplays.zip --output-dir outputs/new_input_runs/my_run --evaluate --provider gemini --api-key YOUR_KEY

# Live run with Groq:
python -m src.pipeline.run_new_input_pack --input path/to/screenplays.zip --output-dir outputs/new_input_runs/my_run --evaluate --provider groq --api-key YOUR_KEY
```

---

## 📊 Output Deliverables

- **Final Ranked Promos**:
  - `outputs/final/final_promos.json` (Structured JSON with rank, duration, formatted timestamps `MM:SS.hh`, hook/cliffhanger, pitch, dimension scores, warnings).
  - `outputs/final/final_promos.csv` (Spreadsheet-ready assignment output).
  - `outputs/final/ranked_promos.json` and `.csv`.
- **Quality & Failure Analysis**:
  - `outputs/reports/quality_report.md` and `outputs/reports/quality_report.json`.
  - `submission/quality_report.md` and `submission/solution_doc.pdf`.
