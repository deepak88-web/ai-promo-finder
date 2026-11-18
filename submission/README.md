# Kuku AI Generalist Assignment - Problem 1: Find the Promos

This folder contains the assignment solution document and output package for Problem 1.

---

## 🚀 Running the Solution

### Option A: Docker (Zero-Configuration)

```bash
docker compose up --build
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### Option B: Local Python Execution

```bash
pip install -r requirements.txt
streamlit run app.py
```
- **Dynamic Key Entry**: You can select your provider (`Gemini`, `Groq`, `OpenAI Compatible`, or `Mock (Offline)`) and enter API keys directly in the sidebar settings. Keys are kept in memory only and never written to `.env`.
- **Sample Pack**: Run the 1-click test on `sample_data/sample_screenplays.zip` from the UI or via CLI:
  ```bash
  python -m src.pipeline.run_new_input_pack --input sample_data/sample_screenplays.zip --output-dir outputs/new_input_runs/sample_run --evaluate --provider mock
  ```

### Option C: Deterministic Offline Unit Tests

```bash
pytest -v
```
All 15 unit tests run locally without network access or API keys.

---

## 📄 Contents

- `solution_doc.pdf`: Clean solution document formatted for review.
- `solution_doc.md`: Source Markdown for the solution document.
- `quality_report.md` & `quality_report.json`: Comprehensive quality, failure, and limitation analysis.
- `walkthrough_script.md`: Narrative walkthrough script explaining the architecture and design decisions.
- `raw_outputs/`: Unedited baseline and expanded promo outputs.
