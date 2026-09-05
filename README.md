# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, source-grounded tutoring, and time-constrained exam optimization.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## Current milestone — expected marks per study hour + Emergency Mode

The backend is now at **v0.28.0**.

StudyOS can now optimize a short remaining study window explicitly around expected grade gain instead of only returning a general priority list.

```text
exam/topic weight
+ current effective mastery
+ personalized learning scale
        ↓
expected marginal mark gain
        ↓
greedy block allocation
        ↓
ordered emergency schedule
+ marks/hour by topic
+ target gap before/after
+ study / defer / skip decisions
```

### Emergency Mode

New endpoint:

```text
POST /api/v1/courses/{course_id}/emergency-plan
```

Example request:

```json
{
  "available_hours": 6,
  "hours_until_exam": 14,
  "target_grade": 25,
  "block_minutes": 30
}
```

The response exposes:

```text
current estimated grade
projected grade after available study time
expected mark gain
target gap before / after
estimated hours to target
urgency
ordered study blocks
next action
per-topic marks/hour
study / defer / skip decisions
```

### Expected marks are not mistake-boosted scores

The ordinary planner can raise priority when repeated mistakes deserve attention. Emergency Mode deliberately separates that from the numeric expected-mark calculation.

A topic's expected gain is derived from:

```text
normalized exam/topic weight
×
change in mastery from the calibrated learning curve
×
course maximum grade
```

Mistake categories remain visible as teaching context but do not inflate a value labelled `expected marks`.

This makes quantities such as:

```text
Momentum
next hour expected gain: 1.2 marks
```

inspectable under the current planning model rather than a disguised priority score.

### Diminishing returns and ordered blocks

The optimizer `expected-marks-greedy-v1` assigns each study block to whichever topic has the largest current marginal expected mark gain.

After a block, that topic's mastery rises and its marginal return falls. Later blocks can therefore move to another topic.

```text
Block 1  Momentum             +0.71 marks
Block 2  Momentum             +0.59 marks
Block 3  Rotational Dynamics  +0.56 marks
Block 4  Momentum             +0.49 marks
...
```

Consecutive blocks on the same topic are grouped in the response for a cleaner actionable schedule.

### Budget-relative skip decisions

Emergency Mode computes a cutoff from both a configurable absolute minimum and a relative fraction of the best current topic return.

Topics receiving no time can be classified as:

```text
study
    receives time in the optimized schedule

defer
    useful return, but stronger topics consume this time budget

skip
    marginal return is below the emergency cutoff
```

`skip` means **skip under this emergency time budget**. It is not stored as a permanent judgment that the course topic is unimportant.

### Urgency context

When `hours_until_exam` is supplied, StudyOS labels the context:

```text
<= 12h   critical
<= 24h   high
<= 72h   elevated
> 72h    standard
omitted  unknown
```

`available_hours` cannot exceed the physical clock time remaining until the exam.

### Model limits

The Emergency Mode response explicitly states that expected marks remain planning heuristics rather than guaranteed exam points. Current stored mastery is retention-adjusted before optimization, but the short-horizon optimizer does not yet model fatigue, context-switch cost, breaks, or additional within-window forgetting.

## Planning and grade modelling

The normal `heuristic-v5` planner combines course importance, exam weight, effective mastery, mistake burden, personalized learning scale, and calibrated retention.

The `probabilistic-v1` layer adds score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Immutable pre-exam forecasts can later receive real outcomes. StudyOS measures prediction error, interval coverage, Brier score, and log loss; guarded empirical recalibration is evaluated with rolling-origin held-out validation.

Emergency Mode is intentionally a separate marginal-value optimizer. Its numeric mark gains do not reuse the planner's mistake-priority multiplier.

## Tutor grounding and retrieval

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval signals include BM25, course-topic evidence, embedding cosine similarity, and a persistent chunk-vector cache.

Generated tutor prose is decomposed into atomic claims and validated locally for citation validity, contradictions, unsupported additions, and numerical consistency before return.

StudyOS also supports adaptive practice, rubric-aware grading, multi-question session memory, remediation teaching, semantic retrieval, persistent incremental embeddings, and hard-negative retrieval benchmarking.

### Retrieval regression suites

Course-level benchmark suites persist labeled queries and relevant chunks. Repeated runs preserve full results and compare bounded ranking metrics against a prior same-K baseline.

```text
Top-1 accuracy
Hit@K
Recall@K
MRR
        ↓
PASS | REGRESSION | NO_BASELINE
```

This lets retrieval changes be measured before adopting additional vector-search infrastructure.

## Intelligence stack

### Course intelligence

- PDF, DOCX, PPTX, TXT, and Markdown ingestion
- page/slide-aware extraction and deterministic chunking
- document classification and deduplication
- course topic graph and source evidence
- past-paper question/mark extraction
- topic frequency and normalized exam weighting

### Diagnostics and mastery

- adaptive diagnostics from real past-paper questions
- Bayesian topic mastery and confidence
- mistake taxonomy and recurring mistake analytics
- response-level mastery history and trends
- forgetting-aware effective mastery
- personalized learning responsiveness and retention calibration
- exam-aware review queue
- practice evidence integrated into the same mastery model

## API highlights

```text
POST /api/v1/courses/{course_id}/documents
POST /api/v1/courses/{course_id}/documents/{document_id}/process
POST /api/v1/courses/{course_id}/analyze
POST /api/v1/courses/{course_id}/exam-intelligence/analyze

POST /api/v1/courses/{course_id}/diagnostics
GET  /api/v1/courses/{course_id}/mastery
GET  /api/v1/courses/{course_id}/mastery/history
GET  /api/v1/courses/{course_id}/mistakes
GET  /api/v1/courses/{course_id}/reviews

POST /api/v1/courses/{course_id}/study-plan
POST /api/v1/courses/{course_id}/emergency-plan
POST /api/v1/courses/{course_id}/grade-forecast
POST /api/v1/courses/{course_id}/grade-forecast/calibrated
GET  /api/v1/courses/{course_id}/forecast-calibration
GET  /api/v1/courses/{course_id}/forecast-validation

POST /api/v1/courses/{course_id}/tutor/search
POST /api/v1/courses/{course_id}/tutor/ask
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs
GET  /api/v1/courses/{course_id}/tutor/embedding-index
POST /api/v1/courses/{course_id}/tutor/embedding-index/sync

POST /api/v1/courses/{course_id}/tutor/practice
POST /api/v1/courses/{course_id}/tutor/practice-sessions
POST /api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate
GET  /api/v1/courses/{course_id}/tutor/practice/{practice_id}/solution
```

FastAPI exposes interactive docs at `/docs` while the server is running.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] source-aware document pipeline
- [x] topic intelligence and past-paper weighting
- [x] study planner

### Phase 2 — Diagnostics and mastery
- [x] adaptive diagnostics and persistent mastery
- [x] mistakes and answer evidence
- [x] forgetting-aware reviews
- [x] mastery history and personalized learning/retention calibration
- [x] deterministic and rubric-aware grading

### Phase 3 — Grade modelling
- [x] probabilistic score distributions and target probabilities
- [x] immutable forecasts and real outcomes
- [x] guarded empirical recalibration
- [x] reliability curves and rolling held-out validation

### Phase 4 — Course-aware tutor
- [x] grounded retrieval and exact citations
- [x] semantic reranking and persistent embedding cache
- [x] adaptive practice, rubric grading, session memory, remediation teaching
- [x] atomic claim validation
- [x] hard-negative retrieval benchmark
- [x] persisted benchmark suites and regression history
- [ ] external ANN/vector backend only when benchmarked scale justifies it

### Phase 5 — Optimization
- [x] expected marks per study hour
- [x] Emergency Mode
- [ ] automatic rescheduling
- [ ] multi-course optimization

### Phase 6 — Study operating system
- [ ] semester dashboard
- [ ] spaced-repetition workflow
- [ ] cheat-sheet generation
- [ ] calendar/focus integration
- [ ] analytics UI
- [ ] PWA/notifications

## Tech stack

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, SQLite, pypdf, python-docx, python-pptx, OpenAI SDK, Pytest, Ruff, and GitHub Actions.

Planned infrastructure includes PostgreSQL, Redis/background workers, an external ANN/vector backend only when benchmarked scale justifies it, Docker, and a Next.js/TypeScript client.

## Local development

```bash
cd backend
python -m venv .venv
pip install -e ".[dev]"
uvicorn app.main:app --reload

ruff check .
pytest
```

The next optimization milestone is **automatic rescheduling**: persist study commitments/completed blocks, compare planned versus actual progress, and reallocate remaining time when a student misses a block, finishes early, or new mastery evidence changes the expected marks/hour ranking.
