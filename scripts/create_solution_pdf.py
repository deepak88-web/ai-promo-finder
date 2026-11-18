"""Render the two-page assignment solution document."""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "submission" / "solution_doc.pdf"

NAVY = colors.HexColor("#15314B")
TEAL = colors.HexColor("#087E8B")
PALE = colors.HexColor("#EEF5F6")
INK = colors.HexColor("#24313D")
MUTED = colors.HexColor("#566575")
RULE = colors.HexColor("#D8E0E5")


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=20, leading=23, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=12, textColor=TEAL, spaceAfter=9,
        ),
        "h": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "BodyCompact", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.2, leading=10.4, textColor=INK, spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.2, leading=9, textColor=MUTED, spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.4, leading=9, textColor=INK,
        ),
        "cellbold": ParagraphStyle(
            "CellBold", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, leading=9, textColor=NAVY,
        ),
        "callout": ParagraphStyle(
            "Callout", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=8.4, leading=11, textColor=NAVY,
        ),
    }


def P(text, style):
    return Paragraph(text, style)


def footer(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.58 * inch, 0.48 * inch, width - 0.58 * inch, 0.48 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.58 * inch, 0.31 * inch, "AI Promo Finder | Kuku Generalist Assignment - Problem 1")
    canvas.drawRightString(width - 0.58 * inch, 0.31 * inch, f"{doc.page} / 2")
    canvas.restoreState()


def build():
    styles = make_styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=letter,
        rightMargin=0.58 * inch, leftMargin=0.58 * inch,
        topMargin=0.55 * inch, bottomMargin=0.62 * inch,
        title="AI Promo Finder - Problem 1 Solution",
        author="AI Promo Finder",
    )
    story = []

    # Page 1: framing, method, and measured run results.
    story += [
        P("AI Promo Finder", styles["title"]),
        P("PROBLEM 1 - FIND THE PROMOS", styles["subtitle"]),
        P("A repeatable, evidence-grounded workflow that turns timestamped screenplays into ranked promo cut lists for editorial review.", styles["body"]),
    ]
    facts = [[
        P("50 episodes", styles["callout"]),
        P("3,727 source events", styles["callout"]),
        P("144 evaluated windows", styles["callout"]),
        P("20-60 sec cuts", styles["callout"]),
    ]]
    fact_table = Table(facts, colWidths=[1.72 * inch] * 4)
    fact_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [fact_table, Spacer(1, 3)]

    story += [
        P("Problem choice and assumptions", styles["h"]),
        P("I chose Problem 1 because editors repeatedly scan episodes for short promotional moments. The prototype narrows that work to source intervals, rankings, and quality review. It does not edit footage, add music, or create overlays. I treat screenplay timestamps as the source of truth; a multi-part promo's duration is the sum of its intervals; editorial order may differ from story chronology. Text alone cannot prove what appears in footage.", styles["body"]),
        P("Workflow", styles["h"]),
        P("1. Parse scenes, dialogue, actions, and timestamps into source events.  2. Layer 1 identifies dramatic events; code forms 20-60 second candidate windows; Layer 2 scores and ranks them.  3. Hook and ending evidence are attached only when source events overlap the opening or ending window.  4. Cross-episode pairs reuse frozen Semantic Verifier V4. Expanded composition adds chronological same-episode montages and one three-part hub candidate from two V4-accepted links.  5. Deterministic validation checks duration, event references, timestamps, duplicate footage, order, and episode metadata.", styles["body"]),
        P("Observed full-pack results", styles["h"]),
    ]

    rows = [
        [P("Run", styles["cellbold"]), P("Output", styles["cellbold"]), P("Qualification", styles["cellbold"])],
        [P("Baseline", styles["cellbold"]), P("100 continuous + 5 two-part cross-episode promos; 105 evaluated", styles["cell"]), P("52 recommend, 40 revise, 13 reject", styles["cell"])],
        [P("Expanded", styles["cellbold"]), P("134 structurally valid; all 134 evaluated with the revised prompt", styles["cell"]), P("68 recommend, 53 revise, 13 reject; 29 new compositions included", styles["cell"])],
    ]
    t = Table(rows, colWidths=[0.85 * inch, 3.25 * inch, 2.78 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("GRID", (0, 0), (-1, -1), 0.45, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 5)]
    story += [
        P("Revised-prompt mean overall score: 6.81/10. Dimension means (/10): hook 6.59, coherence 6.53, flow 7.43, emotional impact 7.10, cliffhanger 6.58, promotional appeal 6.79. Prompt fingerprint: 191b2eedf443787f. Automated scores are not human approval.", styles["small"]),
        PageBreak(),
    ]

    # Page 2: failures, human loop, scale, and run instructions.
    story += [
        P("Quality, limitations, and next use", styles["title"]),
        P("CHECK THE SIGNALS, THEN LET AN EDITOR DECIDE", styles["subtitle"]),
        P("Quality checks and observed failures", styles["h"]),
        P("The expanded structural run has 134 valid cut lists, 0 hard errors, and 225 quality warnings: 36 promos lack identified hook evidence, 26 lack identified cliffhanger evidence, and standalone coherence remains pending for all 134. Structural validity is not an approval of the creative result.", styles["body"]),
        P("Human editorial review is deferred for this prototype. All 134 ledger rows remain pending for hook, cliffhanger, and standalone coherence review; narrative continuity remains pending for multi-segment cuts. Seven recommended promos lack hook evidence and two recommended promos lack cliffhanger evidence. PROMO_EP028_C001 is a notable hook mismatch (7.8 overall, 7/10 automated hook score, recommend, no identified hook evidence).", styles["body"]),
        P("One three-part hub montage is still a draft: each outer segment has a frozen V4 link to the shared event, but the outer segments have no direct V4 link to each other. Automated recommendations and scores do not replace review of source evidence, transitions, or footage.", styles["body"]),
        P("Human review and scale", styles["h"]),
        P("The Streamlit app provides dashboard, rankings, episode explorer, candidate comparison, interactive composition preview, V4 evidence audit, and quality review with downloadable notes. New compositions are clearly marked for fresh scoring and transition review. For a production team, measure editor acceptance, how often cut points move, warning overrides, and click-through/watch-through against the current promo baseline. No production-team outcome or API cost was measured in this run.", styles["body"]),
        P("Reuse and tools", styles["h"]),
        P("The parser accepts ZIP, TXT, or a folder of TXT scripts. Layer 1, Layer 2, and promo evaluation can select Gemini or Groq in .env; evaluator caching includes prompt, provider, and model. New packs write to a separate run directory. The original show's V4 pairs are never reused for a different show. Tools used: Codex for code and analysis; Gemini for saved Layer 1 and the 134-promo revised-prompt evaluation; Groq for saved Layer 2 evaluation. The frozen V4 output was not rerun.", styles["body"]),
        P("Run locally", styles["h"]),
    ]
    run_table = Table([
        [P("Open the app", styles["cellbold"]), P("python -m pip install -r requirements.txt; copy .env.example .env; streamlit run app.py", styles["cell"])],
        [P("Expanded local composition", styles["cellbold"]), P("python -m src.promo_composer.run_promo_pipeline --expanded", styles["cell"])],
        [P("New input pack", styles["cellbold"]), P("python -m src.pipeline.run_new_input_pack --input path\\to\\screenplays.zip --output-dir outputs\\new_input_runs\\my_run", styles["cell"])],
    ], colWidths=[1.55 * inch, 5.33 * inch])
    run_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE),
        ("GRID", (0, 0), (-1, -1), 0.45, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [run_table, Spacer(1, 5)]
    story += [P("Fresh screenplay processing sends text to the configured providers and uses their API quotas. Add --evaluate to score new promos. No public deployment link or walkthrough recording is included; the source repo and a recording script are provided for submission.", styles["small"])]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
