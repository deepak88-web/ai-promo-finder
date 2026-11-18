# AI Promo Finder

A local prototype for Kuku's assignment **Problem 1: Find the Promos**. It parses timestamped screenplay packs, ranks candidate moments, builds 20-60 second cut lists, checks source evidence, and provides a Streamlit review interface.

## Run the existing 50-episode project

1. Create a virtual environment and install the packages in `requirements.txt`.
2. Copy `.env.example` to `.env` and configure the provider keys and provider names you intend to use.
3. Existing raw per-episode outputs and parsed screenplay data are included in the local project workspace. To regenerate the baseline promo composition and validation files, run:

   ```powershell
   python -m src.promo_composer.run_promo_pipeline
   ```

   This reads the saved Semantic Verifier V4 output. It does not run V4.

4. To create the expanded composition set in a separate folder without overwriting baseline promo outputs:

   ```powershell
   python -m src.promo_composer.run_promo_pipeline --expanded
   python scripts/build_quality_report.py
   ```

5. Start the review app:

   ```powershell
   streamlit run app.py
   ```

6. To evaluate all 134 expanded promos with the current prompt and configured promo evaluator provider, run:

   ```powershell
   python -m src.promo_composer.promo_evaluator
   ```

   This uses `outputs/raw/expanded/promo_validation_results.json` and writes its ranking to `outputs/raw/expanded/promo_evaluation.json`. It makes model API calls. Existing baseline evaluation files remain separate.

The app has Dashboard, Global Rankings, Episode Explorer, Candidate Details, Candidate Comparison, Promo Composer, Cross-Episode Discovery, New Input Processing, and Promo Quality Review pages.

## Run on a new screenplay input pack

The parser accepts one ZIP, one TXT file, or a folder of TXT files:

```powershell
python -m src.parser.script_parser --input path\to\screenplays.zip --output outputs\new_input_runs\parsed.json
```

For the full Layer 1/Layer 2 workflow and promo composition, run:

```powershell
python -m src.pipeline.run_new_input_pack --input path\to\screenplays.zip --output-dir outputs\new_input_runs\my_run
```

The full workflow sends screenplay text to the providers selected in `.env` and uses their API quotas. Add `--evaluate` to also run promo-level evaluation. New packs do not reuse the original show's V4 pairs, so cross-episode discovery is left out unless the pack receives its own verified-pair output.

## Provider settings

`LAYER1_PROVIDER`, `LAYER2_PROVIDER`, and `PROMO_EVALUATION_PROVIDER` accept `gemini` or `groq`. Layer 1 and Layer 2 default to Groq. Promo evaluation defaults to Gemini. Set `GEMINI_API_KEY`/`GROQ_API_KEY` and the provider-specific model names in `.env`. The promo evaluator fingerprints its prompt, provider, and model so cached scores are not silently reused across configurations.

## Output locations

- Baseline outputs: `outputs/raw/`.
- Expanded composition output: `outputs/raw/expanded/`.
- Quality report: `outputs/reports/promo_quality_report.md` and `.json`.
- Assignment package: `submission/`.

The expanded run adds same-episode montages and V4-linked hub candidates. They are cut-list suggestions, not publish approvals. New compositions are marked for editorial review. After the expanded evaluator run, the Streamlit quality page uses the 134-promo ranking.

## Checks

Run local deterministic checks without calling any model API:

```powershell
python -m pytest tests/test_local_workflows.py -q
```

The older `tests/test_semantic_verifier.py` invokes Gemini and can overwrite the frozen V4 file. Do not run it for this assignment.
