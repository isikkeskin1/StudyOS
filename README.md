# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, source-grounded tutoring, and time-constrained exam optimization.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## Current milestone — persistent Emergency Mode + automatic rescheduling

The backend is now at **v0.29.0**.

Emergency Mode is no longer limited to a one-shot calculation. StudyOS can persist an optimized study schedule, record what actually happened, and rebuild only the unfinished portion when time or mastery changes.

```text
expected-marks emergency plan
        ↓
persist schedule revision 1
        ↓
start / complete / skip blocks
        ↓
actual minutes + new mastery evidence
        ↓
recompute remaining budget
        ↓
expected-marks optimizer
        ↓
persist revision 2, 3, ...
```

### Stateless calculation and persistent execution

The original endpoint remains available as a stateless calculator:

```text
POST /api/v1/courses/{course_id}/emergency-plan
```

For a schedule that survives reloads and changes over time, use:

```text
POST /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}
```

Creating a persisted schedule snapshots the current Emergency Mode result as revision 1. The collection endpoint lets a client rediscover schedules after an app reload rather than depending on an in-memory ID.

### Block lifecycle

Current-revision blocks can be acted on through:

```text
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/start
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/complete
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/skip
```

Block states are:

```text
planned
in_progress
completed
skipped
superseded
```

Only current-revision unfinished blocks can be mutated. Once a replan occurs, old unfinished blocks become `superseded`; completed and skipped blocks remain as historical evidence of what actually happened.

Only one current block can be `in_progress` at a time.

### Actual time changes the remaining budget

Completing a block records `actual_minutes` instead of assuming the planned duration was exact.

```text
planned 30 min, completed in 15
→ only 15 minutes consumed
→ 15 minutes remain available elsewhere

planned 30 min, took 45
→ 45 minutes consumed
→ remaining plan shrinks by the extra 15
```

Skipping a block defaults to treating that planned block duration as lost time. A caller may provide an explicit `lost_minutes` value when reality differs.

Manual refresh is available through:

```text
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule
```

A manual refresh may reduce the remaining study budget, but it cannot invent more time than the schedule currently has available.

### Revision history is immutable

Every successful replan with remaining time creates a new revision rather than rewriting the old plan.

```text
revision 1  initial
revision 2  completed_early
revision 3  missed_block
revision 4  manual_refresh
```

Each revision snapshots:

```text
remaining minutes
current estimated grade
projected grade
expected mark gain
target gap after the remaining plan
mastery basis
ordered study blocks
```

This makes the schedule auditable: StudyOS can show what it originally recommended, what changed, and why the later plan is different.

### Study projections do not become fake mastery evidence

Completing a study block does **not** write directly to `TopicMastery`.

Instead, the schedule can apply the existing learning curve as a local planning projection when rebuilding the unfinished plan:

```text
measured mastery
+ completed study after that measurement
        ↓
schedule-local projected mastery
```

That projection only affects the schedule. Real diagnostic or practice responses remain the source of measured mastery evidence.

If a newer `TopicMastery` measurement exists, StudyOS starts from that newer evidence and only projects completed study that happened after it. This prevents older schedule projections from being double-counted on top of a fresh diagnostic result.

A manual refresh therefore can change the next topic immediately when new measured mastery changes the expected marks/hour ranking.

### Wall-clock deadline still wins

When the schedule was created with `hours_until_exam`, StudyOS persists the resulting exam deadline. Every reschedule caps the remaining study budget by both:

```text
remaining declared study budget
and
actual wall-clock time until the exam
```

The schedule cannot continue allocating study blocks past the exam simply because the original plan had unused minutes left.

### Expected-marks optimizer

The underlying optimizer remains `expected-marks-greedy-v1`.

A topic's numeric expected gain is derived from:

```text
normalized exam/topic weight
×
change in mastery from the calibrated learning curve
×
course maximum grade
```

Mistake categories can influence teaching context but do not inflate a number labelled `expected marks`. Expected marks remain planning heuristics rather than guaranteed exam points.

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
POST /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule
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
- [x] persistent schedules and automatic rescheduling
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

The next optimization milestone is **multi-course optimization**: let courses compete for scarce study time using a normalized objective that respects different grade scales, targets, deadlines, and evidence uncertainty rather than naively comparing raw marks/hour across unrelated exams.
