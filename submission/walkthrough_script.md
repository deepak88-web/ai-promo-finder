# 2-3 Minute Walkthrough Recording Script

Target length: about 2 minutes 30 seconds. Record the Streamlit app in your own voice; use the local 50-episode results and avoid showing API keys or the screenplay ZIP.

## 0:00-0:20 - Set the scope

"I chose Problem 1: finding short promos from timestamped screenplays. The prototype identifies source intervals and ranks promo candidates. It does not edit footage, add music, or create overlays."

## 0:20-0:45 - Dashboard and ranking

Open **Dashboard**, then **Global Rankings**. Point out that the existing full-pack run produced 105 evaluated promos and show how scores and episode filters work.

"The rankings are recommendations from a text-based evaluator, not a claim that the actual footage has been reviewed."

## 0:45-1:15 - Compare and explore

Open **Episode Explorer** and **Candidate Comparison**. Show one episode's candidate timestamps and compare two candidates' scores, strengths, and weaknesses.

## 1:15-1:45 - Compose and verify

Open **Promo Composer**. Pick a three-segment same-episode candidate or a verified cross-episode candidate. Show the ordered episode/time intervals, summed duration, and manual-review label. Open **Cross-Episode Discovery** and point to the V4 pair IDs and evidence excerpts.

"The three-part hub option connects each spoke to the shared anchor. The spoke-to-spoke cut is not verified, so it stays a review candidate."

## 1:45-2:15 - Quality review and limitations

Open **Promo Quality Review**. Show a missing hook or cliffhanger warning, then a new composition marked evaluation pending. Explain that chronology or event evidence alone cannot establish attention, suspense, or standalone clarity.

"One failure we found: the baseline evaluator recommended PROMO_EP028_C001 with a 7 out of 10 hook score even though the validator found no opening hook evidence. That is why the review page keeps those signals separate."

## 2:15-2:30 - Reuse

Open **New Input Processing** without starting a run. Show accepted ZIP/TXT inputs and explain that the workflow uses the selected Gemini/Groq providers. Mention that fresh model processing uses API quota, and that V4 is not rerun by the expanded composer.
