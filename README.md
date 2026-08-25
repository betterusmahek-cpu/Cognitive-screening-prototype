# Multidomain Screening & Classification Prototype

**LLM-Assisted Multidomain Screening and Classification System for ADHD and
Cognitive Impairment — research prototype.**

> ⚠️ **This is a research screening prototype, not a diagnostic system.**
> It never claims to clinically diagnose ADHD, MCI, dementia, or any other
> disorder. Every output is labeled a *screening classification*, not a
> diagnosis, and every result page states this explicitly.

---

## What this is

A 30-item questionnaire covering attention, hyperactivity/impulsivity,
developmental history, memory, executive function, language, orientation,
cognitive decline, and functional independence. Responses are collapsed into
ten **domain scores**, which a transparent, rule-based classifier maps to one
of five research categories:

1. Probable ADHD
2. Probable MCI
3. Probable Dementia
4. Likely Healthy
5. Other / Indeterminate

```
Questionnaire
      │
Structured feature extraction (deterministic, always available)
      │
LLM-assisted interpretation (optional — same schema, used only if
requested and configured; falls back to deterministic on any failure)
      │
Domain-level feature vector (10 features, 0–4 each)
      │
Deterministic rule-based classifier
      │
Five-category screening result + confidence + rationale + disclaimer
```

The LLM, when enabled, is only ever asked to convert answers into the same
structured feature schema the deterministic scorer produces — it is never
asked to diagnose. See `api/_lib/llm.py`.

## Project layout

```
api/
  questions.py        GET  /api/questions  — questionnaire + sections + scales
  screen.py            POST /api/screen     — validate → score → classify
  _lib/
    questions_data.py  Single source of truth for question text/domains/scales
    scoring.py          Domain scoring + interpretable classifier
    llm.py               Optional LLM feature extraction, with strict
                          schema validation and automatic fallback
public/
  index.html           One-question-at-a-time questionnaire + results UI
  style.css            Design system (IBM Plex type trio, instrument panel)
  app.js               Client logic: fetch questions, drive flow, submit,
                        render the results "signal panel"
vercel.json            Declares the two Python serverless functions
requirements.txt        Stdlib-only today; documents where to pin deps later
```

No local Flask server is required — both endpoints are plain
`http.server.BaseHTTPRequestHandler` functions in the shape Vercel's Python
runtime expects, and `public/` is served automatically as static assets.

## Running locally

Vercel's CLI is the easiest way to run the Python functions and static
frontend together exactly as they'll run in production.

```bash
npm install -g vercel      # if you don't already have it
vercel dev
```

Then open the printed local URL (typically `http://localhost:3000`).

## Deploying to Vercel

```bash
git init
git add .
git commit -m "Initial prototype"
git remote add origin <your-repo-url>
git push -u origin main
```

Then, in the Vercel dashboard:

1. **Import Project** → select the repository.
2. Vercel auto-detects the Python functions in `api/` and the static site in
   `public/`. No build command is required.
3. (Optional) Add environment variables — see below.
4. Deploy.

No local server is needed in production; everything above runs as it will on
Vercel.

## Environment variables (optional)

The system works fully **without** any environment variables — it just uses
deterministic questionnaire scoring.

| Variable          | Required | Purpose                                                   |
|-------------------|----------|------------------------------------------------------------|
| `OPENAI_API_KEY`  | No       | Enables the optional LLM feature-extraction path           |
| `OPENAI_MODEL`    | No       | Overrides the default model (`gpt-4o-mini`)                 |

Set these in the Vercel dashboard under **Project → Settings →
Environment Variables**. Never commit a `.env` file — `.gitignore` already
excludes it, and the key is only ever read server-side (`os.environ`); it is
never sent to or embedded in frontend JavaScript.

If `use_llm: true` is sent to `/api/screen` but no key is configured, or the
LLM call fails or returns invalid JSON for any reason, the system silently
and automatically falls back to deterministic scoring — the participant
always gets a result.

## API reference

### `GET /api/questions`

Returns the questionnaire, section metadata, and scale label sets:

```json
{
  "questions": [ { "id": 1, "text": "...", "domain": "attention", "scale": "frequency" }, ... ],
  "sections": [ { "id": "attention", "title": "Attention & Focus", "range": [1, 7] }, ... ],
  "scales": { "frequency": [ { "value": 0, "label": "Never" }, ... ], "change": [...], "independence": [...] }
}
```

### `POST /api/screen`

Request:

```json
{
  "answers": { "1": 3, "2": 2, "3": 1, "...": "...", "30": 0 },
  "use_llm": false
}
```

`answers` must include all 30 question ids (as string or numeric keys) with
integer values 0–4. `use_llm` is optional and defaults to `false`.

Response:

```json
{
  "label": "Probable ADHD",
  "confidence": 0.78,
  "scores": {
    "Probable ADHD": 3.1,
    "Probable MCI": 1.4,
    "Probable Dementia": 0.9,
    "Likely Healthy": 1.8
  },
  "domains": {
    "attention": 3.4, "hyperactivity": 2.0, "impulsivity": 1.5,
    "childhood_history": 3.4, "memory": 0.8, "executive": 1.2,
    "language": 0.5, "orientation": 0.2, "cognitive_decline": 0.4,
    "functional_impairment": 0.3
  },
  "contributing_domains": ["attention", "childhood_history"],
  "rationale": "The response pattern shows elevated attention-related difficulties...",
  "disclaimer": "This is a research screening result, not a clinical diagnosis. ...",
  "meta": { "extraction_method": "deterministic" }
}
```

`confidence` is a **prototype/model confidence**, not a calibrated clinical
probability — it has not been validated against outcome data.

Error responses are always `{"error": "<participant-safe message>"}` with an
appropriate status code (`400` invalid input, `413` oversized payload, `500`
unexpected server error). Internal exceptions, stack traces, and API keys are
never included in a response.

## Classifier design

See `api/_lib/scoring.py` for the full, commented implementation. In brief:

- Ten domain scores are computed as the mean of their mapped questionnaire
  items (never a flat sum of all 30 items).
- Each of the four named categories gets a raw **evidence score** from a
  documented weighted combination of domain scores.
- Explicit guardrails then decide the final label:
  - If the top evidence score is low, or the top two are close together, the
    result is **Other / Indeterminate** rather than a forced category.
  - **Probable ADHD** additionally requires some endorsement of developmental
    history — attention difficulties alone, without childhood history, fall
    back to Indeterminate.
  - Functional impairment is the explicit differentiator between **Probable
    MCI** and **Probable Dementia**, per the project's clinical design
    principle.
- The result always includes the full evidence-score breakdown, the domain
  vector, a short rationale, and the disclaimer — nothing is a black box.

These weights and thresholds are prototype defaults, not fitted to data. They
are intentionally centralized as named constants at the top of
`scoring.py` for easy revision.

## Privacy & security

- No name, phone number, address, government ID, or other identifying
  information is ever requested by the questionnaire.
- Participant responses are **not stored** by this prototype — `/api/screen`
  is stateless; it scores the submitted payload and returns a result with
  nothing persisted server-side.
- `OPENAI_API_KEY` is read only from server-side environment variables and
  never appears in any frontend code, build artifact, or client response.
- `.env` files are excluded via `.gitignore` — never commit one.

## Research roadmap (not yet implemented)

This prototype ships the rule-based classifier and the questionnaire/API/UI
scaffold described above. The following are explicitly **out of scope for
this codebase today** and are documented here so the intended research path
is clear:

- A labeled dataset (`participant_id`, age, `q1`…`q30`, domain scores,
  independently-established reference label — never the LLM's own output
  used as ground truth, to avoid circular evaluation).
- Training and evaluating ML classifiers (logistic regression, SVM, random
  forest, XGBoost) on a held-out test set, with accuracy, precision, recall,
  macro-F1, confusion matrices, per-class performance, calibration, and error
  analysis.
- A hybrid LLM + rule/ML comparison, per the project's four-way evaluation
  plan (rule-based / LLM-only / traditional ML / hybrid).

No claim of DSM-5 validation, clinical validation, or diagnostic accuracy
should be added anywhere in this project unless it is backed by that kind of
evidence.
