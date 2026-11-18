# 3-Minute Video Walkthrough Script & Transcript

**Target Duration**: 2 minutes 45 seconds to 3 minutes  
**Goal**: Explain the problem, architecture, evaluation funnel, Streamlit interface, and deliverables for **Problem 1: Find the Promos** (Kuku AI Generalist Assignment).

---

### [0:00 – 0:30] Hook & Problem Overview
*(Visual Cue: Show Streamlit Dashboard or title slide with AI Promo Finder)*

> **Spoken**:  
> "Hi everyone, today I'm presenting **AI Promo Finder**, built for Kuku's Problem 1: finding high-converting, 20 to 60-second audio promos from timestamped screenplay packs.  
> 
> In narrative audio, a great promo cannot simply be a random excerpt. It requires three non-negotiable qualities: a strong opening hook within the first 3 seconds, narrative coherence that makes sense without prior context, and a gripping unresolved cliffhanger at the end.  
> 
> Rather than relying on a naive end-to-end LLM prompt that suffers from context loss and hallucinated timestamps, our system implements a grounded, multi-stage hierarchical funnel."

---

### [0:30 – 1:15] Architecture & The Funnel
*(Visual Cue: Switch to Global Rankings / Episode Explorer)*

> **Spoken**:  
> "Our architecture breaks down the screenplay into a four-stage deterministic pipeline:
> 
> 1. **Parsing & Dramatic Identification (Layer 1)**: The script parser normalizes scene timestamps and speakers. Layer 1 uses fast reasoning models like Groq or Gemini to isolate pivotal dramatic turning points, conflict beats, and reveals.
> 2. **Candidate Window Expansion**: We mathematically expand each event into valid candidate windows while preserving verbatim dialogue excerpts and calculating exact source timestamps.
> 3. **Candidate Evaluation (Layer 2)**: Candidates are scored across six dimensions—hook potential, emotional intensity, suspense, coherence, promotional value, and ending strength.
> 4. **Composition & Validation**: Individual moments and chronological same-episode montages are assembled. Exact segment durations are summed down to the millisecond, strictly enforcing the 20 to 60-second constraint."

---

### [1:15 – 2:00] Grounding, Evaluator & Quality Review
*(Visual Cue: Switch to 'Promo Quality Review' tab and select a top promo)*

> **Spoken**:  
> "On the **Promo Quality Review** page, every promo is validated against the raw screenplay. Opening hooks and closing cliffhangers are strictly grounded in verified event IDs within their respective 3-second boundary windows.  
> 
> Promos are then evaluated by a comprehensive evaluator across six weighted criteria: opening hook, standalone coherence, narrative flow, emotional impact, cliffhanger effectiveness, and promotional appeal. 
> 
> Our decision logic is fully deterministic: scores of 7.0 or higher are recommended, 5.0 to 6.9 are flagged for revision, and below 5.0 are rejected—with automatic downgrade if standalone coherence falls below 5.0."

---

### [2:00 – 2:30] Streamlit UI, Security & Dynamic Model Selection
*(Visual Cue: Click the sidebar 'Model & API Settings', open the 'Configure API Key' popup, and show New Input Processing)*

> **Spoken**:  
> "For the frontend, we built an interactive Streamlit application designed for both production deployment and instant testing:
> 
> In the sidebar, users can dynamically select their provider—Gemini, Groq, OpenAI-compatible endpoints, or an offline Mock mode. 
> 
> For security, API keys are entered via a modal popup and stored strictly in session memory—they are never exposed on screen, baked into the image, or written to disk.
> 
> Users can run a one-click test on our bundled sample pack, upload custom screenplay ZIPs, and immediately export standardized `final_promos.json` and `final_promos.csv` deliverables with formatted timestamps."

---

### [2:30 – 3:00] Verification, Docker & Conclusion
*(Visual Cue: Show terminal running `pytest -v` passing all 14 tests, and show `docker compose up`)*

> **Spoken**:  
> "To guarantee engineering rigor, the entire system includes a suite of 15 deterministic offline tests covering parser edge-cases, window generator logic, multi-provider routing, and end-to-end execution with zero network dependency.
> 
> Furthermore, the application is completely Dockerized and production-ready for deployment on Render, Docker Compose, or Streamlit Cloud with a single command: `docker compose up --build`.
> 
> AI Promo Finder transforms raw text into auditable, high-converting promo cut lists grounded in dramatic evidence. Thank you!"
