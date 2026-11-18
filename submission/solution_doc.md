# AI Promo Finder - Problem 1: Find the Promos

## Problem choice and scope

I chose Problem 1 because editors must repeatedly scan timestamped episodes for short, usable promotional moments. The prototype narrows that work to timestamped cut lists, rankings, and quality review across the provided 50-episode pack. It does not edit video, add music, or create overlays.

Assumptions: screenplay event timestamps are the source of truth; a multi-part promo's duration is the sum of its source intervals; editorial order may differ from story chronology; screenplay text cannot prove what a viewer sees in the footage. Human review remains necessary for transitions, hook strength, unresolved endings, and standalone clarity.

## How it works

1. Parse screenplay scenes, dialogue, actions, and timestamps into source events.
2. Use Layer 1 to identify dramatic events, code to form 20-60 second windows, and Layer 2 to score candidate windows.
3. Rank source candidates; attach hook and ending evidence only when a source event overlaps the opening or ending window.
4. For cross-episode links, reuse the frozen Semantic Verifier V4 file. The expanded composer also assembles chronological same-episode montages and a three-part hub montage from two V4-accepted links that share an event.
5. Validate source timestamps, durations, duplicate footage, segment order, and episode metadata. The Streamlit app supports ranking, comparison, episode exploration, composition review, and downloadable editorial notes.

## Results from saved runs

| Run | Observed result |
|---|---|
| Full input pack | 50 episodes, 3,727 screenplay events, 144 evaluated Layer 2 candidates |
| Baseline promo run | 100 continuous promos + 5 two-part cross-episode promos; 105 evaluated and ranked |
| Baseline decisions (original 105-promo run) | 52 recommend, 40 revise, 13 reject |
| Expanded composition run | 100 continuous + 23 two-part + 11 three-part promos; 134 structurally valid, 0 hard errors |
| Refreshed expanded evaluation | All 134 promos evaluated with revised prompt; 68 recommend, 53 revise, 13 reject; 29 new compositions included |
| Expanded structural review | 225 warnings; 36 missing-hook evidence, 26 missing-cliffhanger evidence, and 134 standalone-coherence-pending warnings |

The refreshed evaluator uses Gemini `gemini-3.5-flash-lite` with prompt fingerprint `191b2eedf443787f`. Its mean dimension scores are reported in `outputs/reports/quality_report.json`. These scores are automated assessments, not human editorial approval.

## Quality checks, failures, and limits

In the expanded run, 36 promos lack identified hook evidence, 26 lack identified cliffhanger evidence, and all 134 remain pending standalone-coherence review. Structural validity only means the source cut list passes deterministic checks; it does not certify that a promo is compelling. Human editorial review is deferred for this prototype: the 134-row ledger keeps hook, cliffhanger, coherence, and editorial decisions pending, and narrative continuity remains pending for multi-segment cuts. The 29 new compositions are included in the revised-prompt evaluator run but still require editorial review.

One evaluator mismatch: PROMO_EP028_C001 received a 7/10 opening-hook score and a recommend decision even though the validator found no opening-hook evidence. Seven recommended promos lack hook evidence; two recommended promos lack cliffhanger evidence. The app and review ledger surface these for later review. The three-part cross-episode hub montage is also a draft: each spoke is linked to the shared event by a frozen V4 pair, but there is no direct V4 edge between the spokes.

At real-team scale, track editor acceptance, how often cut points move, warning override rates, and click-through/watch-through against the team's current promo baseline. No production-team outcome or API cost measurement is available in this local assignment run.

## Reuse and tools

The parser accepts ZIP, TXT, and folders of TXT screenplays. Layer 1, Layer 2, and promo evaluation can select Gemini or Groq in `.env`; prompt/provider/model fingerprints prevent reusing evaluations under a changed configuration. New input runs are separated into their own output folder. Cross-episode links are not carried over to a different show without a new verified-pair result.

Tools used: Codex for code, analysis, and documentation; Gemini for the saved Layer 1 and refreshed 134-promo evaluation; Groq for the saved Layer 2 evaluations. The frozen Semantic Verifier V4 output was not rerun. Final report generation uses saved outputs and makes no model calls.

## Run it

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

For expanded local composition and quality reporting without model calls:

```powershell
python -m src.promo_composer.run_promo_pipeline --expanded
python scripts/build_quality_report.py
```
