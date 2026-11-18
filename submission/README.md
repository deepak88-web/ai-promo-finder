# Kuku AI Generalist Assignment - Problem 1

This folder contains the assignment solution document and raw output package. The prototype runs locally from the repository; no public deployment or repository link has been created.

## Prototype

From the repository root:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Add provider API keys to .env before running model stages.
streamlit run app.py
```

The Streamlit app opens the existing 50-episode outputs. Its **New Input Processing** page accepts a screenplay ZIP or TXT files and runs the reusable pipeline. Model processing sends screenplay text to the configured providers and can use their API quotas.

To refresh only local composition and validation outputs without model calls or rerunning frozen Semantic Verifier V4:

```powershell
python -m src.promo_composer.run_promo_pipeline --expanded
python scripts/build_quality_report.py
```

To score all 134 expanded promos with the current evaluator (this makes model API calls and preserves the baseline evaluation), run:

```powershell
python -m src.promo_composer.promo_evaluator
```

## Contents

- `solution_doc.pdf`: two-page solution document for the assignment form.
- `solution_doc.md`: editable source of the solution document.
- `walkthrough_script.md`: a short recording outline; no video has been recorded.
- `raw_outputs/`: unedited baseline and expanded JSON outputs, plus the frozen V4 input and SHA-256 manifest.

The screenplay input pack is confidential. This package contains derived promo output only; do not publish the source screenplay or input pack.
