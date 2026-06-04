# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, and source-grounded tutoring.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS is trying to answer

- What should I study next?
- Which topics matter most for the exam?
- How many focused hours should I invest?
- What grade is realistic with the time I have?
- What is the probability of reaching my target grade?
- Why am I repeatedly losing marks?
- Which topics are becoming stale and need review?
- Does this student learn or forget a topic faster than the generic model assumes?
- Are StudyOS forecasts accurate and calibrated against real outcomes?
- Can the tutor answer from my actual lectures, notes, exams, and solutions with exact citations?
- What should I deprioritize when time is running out?

## Current milestone — course-aware grounded tutor retrieval

The backend is now at **v0.16.0**.

StudyOS can search processed course material and answer conservatively from retrieved evidence while preserving exact source references.

Current tutor behavior:

- searches only documents belonging to the requested course
- uses processed source-aware chunks from PDF, PPTX, DOCX, TXT, and Markdown uploads
- ranks chunks with deterministic `lexical-bm25-v1` retrieval
- optionally filters retrieval by classified document type
- returns document name, document type, chunk id, source label, locator type/index, excerpt, relevance score, query-term coverage, and matched terms
- preserves references such as `lecture-slides.pptx — slide 4` or `exam.pdf — page 3`
- exposes a deterministic `extractive-grounded-v1` answer mode
- adds inline citation markers such as `[1]`
- refuses to synthesize an answer when retrieved evidence is below the requested relevance threshold
- refuses to turn merely related text into an unsupported explanation
- keeps the retrieval/answer contract independent from any future LLM provider

This first tutor milestone is intentionally retrieval-first. StudyOS does **not** claim that the extractive answerer is a full AI tutor. The next tutor layer can use an LLM to synthesize explanations from the same retrieved citation packet without weakening source grounding.

## Tutor API

### Search course material

```text
POST /api/v1/courses/{course_id}/tutor/search
```

Example request:

```json
{
  "query": "net force acceleration",
  "limit": 6,
  "document_types": ["lecture", "notes"]
}
```

A result exposes fields such as:

```text
document_name
source_label
locator_type
locator_index
source_reference
excerpt
relevance_score
term_coverage
matched_terms
```

### Ask from course material

```text
POST /api/v1/courses/{course_id}/tutor/ask
```

Example:

```json
{
  "question": "What does Newton's second law say about force and acceleration?",
  "max_sources": 6,
  "minimum_relevance": 0.20
}
```

Supported responses identify:

```text
answer_mode: extractive-grounded-v1
retrieval_model: lexical-bm25-v1
grounding_status: supported
citation_coverage: 1.0
```

If the current course material cannot support the question:

```text
grounding_status: insufficient_evidence
citation_coverage: 0.0
citations: []
```

The service then explicitly declines to guess.

## Existing intelligence stack

Before tutoring, StudyOS already builds a fairly deep student/course model.

### Course intelligence

- course creation and persistence
- upload/deduplication for `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md`
- source-aware extraction
- PDF page and PowerPoint slide references
- document classification
- chunking
- course topic graph
- source evidence and topic relationships
- past-paper question extraction
- explicit mark extraction
- topic frequency and normalized exam weighting

### Diagnostics and mastery

- adaptive diagnostics using actual past-paper questions
- persistent Bayesian topic mastery
- mastery confidence and evidence weighting
- answer capture
- deterministic solution-grounded grading where a trustworthy reference exists
- mistake taxonomy and recurring mistake analytics
- response-level mastery history
- trend analytics
- forgetting-aware effective mastery
- personalized learning responsiveness
- retention-half-life calibration from time-separated evidence
- exam-aware review queue

### Planning

The current `heuristic-v5` planner combines:

```text
course importance
+ past-paper exam weight
+ effective mastery after forgetting
+ mistake patterns
+ personalized learning scale
+ calibrated retention
→ study allocation
```

Explicit topic mastery overrides remain available and are not silently decayed.

### Probabilistic grade modelling

The raw forecasting layer is `probabilistic-v1`.

It provides:

- expected grade
- uncertainty / standard deviation
- configurable likely-score interval
- probability of reaching the target
- probabilities for arbitrary score thresholds
- study-hour scenarios
- estimated hours for a requested probability of reaching a target
- evidence-quality-driven uncertainty width

Probability outputs remain labelled provisional rather than falsely presented as guaranteed statistical calibration.

## Forecast outcome calibration

StudyOS can persist immutable pre-exam forecast snapshots and attach the eventual real grade afterward.

It measures:

```text
MAE
RMSE
signed bias
interval coverage
coverage gap
Brier score
log loss
target-probability calibration gap
```

### Guarded empirical recalibration

`empirical-v1` can adjust future score bias and uncertainty width, but only conservatively:

```text
0–4 outcomes    inactive
5–9 outcomes    guarded
10–29 outcomes  developing
30+ outcomes    measured
```

Corrections are confidence-shrunk, capped, and kept separate from the raw forecast.

Adjusted snapshots preserve a one-to-one raw forecast artifact so later calibration trains against original predictions instead of recursively learning from previous corrections.

### Rolling held-out validation

StudyOS does not judge recalibration only by in-sample fit.

`GET /api/v1/courses/{course_id}/forecast-validation` performs chronological rolling-origin validation:

```text
Outcomes 1–5 known
      ↓
fit empirical-v1
      ↓
forecast 6 is held out
      ↓
outcome 6 arrives
      ↓
compare raw vs recalibrated
```

The evaluated forecast's own outcome is never used to recalibrate that forecast.

Held-out comparisons use the same exams for both models and compare:

```text
MAE
RMSE
signed bias
interval coverage
coverage gap
Brier score
log loss
```

StudyOS also exposes fixed reliability buckets:

```text
0–20%
20–40%
40–60%
60–80%
80–100%
```

with predicted-vs-observed target-hit rates and sample counts.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create a course |
| `GET` | `/api/v1/courses` | List courses |
| `GET` | `/api/v1/courses/{course_id}` | Get one course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload material |
| `GET` | `/api/v1/courses/{course_id}/documents` | List material |
| `POST` | `/api/v1/courses/{course_id}/documents/{document_id}/process` | Extract/classify material |
| `GET` | `/api/v1/courses/{course_id}/documents/{document_id}/content` | Read source units/chunks |
| `POST` | `/api/v1/courses/{course_id}/analyze` | Build course intelligence |
| `GET` | `/api/v1/courses/{course_id}/intelligence` | Read topic intelligence |
| `POST` | `/api/v1/courses/{course_id}/exam-intelligence/analyze` | Analyze past papers |
| `GET` | `/api/v1/courses/{course_id}/exam-intelligence` | Read exam intelligence |
| `POST` | `/api/v1/courses/{course_id}/diagnostics` | Start adaptive diagnostic |
| `GET` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/next` | Get next question |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/responses` | Score/store response |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/grade` | Auto-grade from extracted solution |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read raw mastery |
| `GET` | `/api/v1/courses/{course_id}/mastery/history` | Read mastery history/trends |
| `GET` | `/api/v1/courses/{course_id}/calibration` | Read learning/retention calibration |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read mistake analytics |
| `GET` | `/api/v1/courses/{course_id}/reviews` | Read review queue |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Build study plan |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast` | Raw probabilistic forecast |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast/calibrated` | Raw + empirical forecast |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots` | Persist pre-exam forecast |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots/{snapshot_id}/outcome` | Attach actual grade |
| `GET` | `/api/v1/courses/{course_id}/forecast-calibration` | Historical forecast metrics |
| `GET` | `/api/v1/courses/{course_id}/forecast-validation` | Held-out model validation |
| `POST` | `/api/v1/courses/{course_id}/tutor/search` | Search grounded course evidence |
| `POST` | `/api/v1/courses/{course_id}/tutor/ask` | Answer conservatively from course evidence |

FastAPI exposes interactive API docs at `/docs` while the server is running.

## Roadmap

### Phase 1 — Course intelligence and planning

- [x] course/document model
- [x] source-aware extraction and chunking
- [x] topic intelligence
- [x] past-paper weighting
- [x] first planning engine

### Phase 2 — Diagnostics and mastery

- [x] adaptive diagnostics
- [x] persistent mastery/confidence
- [x] mistakes and answer evidence
- [x] solution-grounded deterministic grading
- [x] forgetting-aware mastery/reviews
- [x] mastery history/trends
- [x] personalized learning/retention calibration
- [ ] richer rubric/LLM grading adapter

### Phase 3 — Grade modelling

- [x] probabilistic score distributions
- [x] target probabilities and study-hour scenarios
- [x] immutable forecasts and real outcomes
- [x] empirical calibration metrics
- [x] guarded empirical recalibration
- [x] raw-vs-adjusted audit trail
- [x] reliability curves
- [x] chronological rolling held-out validation

### Phase 4 — Course-aware tutor

- [x] deterministic course-chunk retrieval
- [x] exact page/slide/document citations
- [x] course isolation and document-type filtering
- [x] grounded extractive answer fallback
- [x] insufficient-evidence refusal
- [ ] semantic/vector retrieval
- [ ] LLM synthesis constrained to retrieved evidence
- [ ] citation verification / claim-to-source coverage
- [ ] exam-style question generation from course material
- [ ] guided problem solving and hint progression
- [ ] tutor personalization from mastery/mistake state

### Phase 5 — Optimization

- [ ] expected marks per study hour
- [ ] emergency mode
- [ ] automatic rescheduling
- [ ] multi-course optimization

### Phase 6 — Study operating system

- [ ] semester dashboard
- [ ] spaced repetition workflow
- [ ] cheat-sheet generation
- [ ] calendar/focus integration
- [ ] analytics UI
- [ ] PWA/notifications

## Tech stack

**Current**

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2
- SQLite
- pypdf
- python-docx
- python-pptx
- Pytest
- Ruff
- GitHub Actions

**Planned**

- Next.js / TypeScript
- PostgreSQL
- Redis/background workers
- semantic/vector retrieval
- Docker
- LLM-assisted tutoring/grading

## Local development

```bash
cd backend
python -m venv .venv
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run checks:

```bash
ruff check .
pytest
```

## Typical end-to-end flow

1. Create a course with target grade and exam date.
2. Upload and process lectures, notes, past papers, and solutions.
3. Build course and exam intelligence.
4. Run diagnostics to collect measured mastery evidence.
5. Inspect mistakes, mastery history, calibration, and review queue.
6. Generate an adaptive study plan.
7. Explore raw/calibrated grade forecasts.
8. Save a pre-exam forecast and attach the real result afterward.
9. Use forecast calibration/validation to measure whether the model improves.
10. Use `/tutor/search` or `/tutor/ask` to retrieve explanations directly from processed course material.

The next Phase 4 milestone is **semantic retrieval + an LLM synthesis adapter that is forced to cite the retrieved evidence and can refuse unsupported claims**.
