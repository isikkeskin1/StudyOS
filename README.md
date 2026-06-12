# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, source-grounded tutoring, and time-constrained exam optimization.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## Current milestone — spaced-repetition workflow

The backend is now at **v0.33.0**.

Due reviews now launch persistent, single-question review sessions. Selection uses the
existing calibrated retention queue and its topic priority. An optional `topic_id`
selects a specific due topic. Repeated starts resume unfinished work; skipped or
solution-revealed reviews can be restarted without recording mastery evidence.

```text
POST /api/v1/courses/{course_id}/review-sessions
GET  /api/v1/courses/{course_id}/review-sessions
GET  /api/v1/courses/{course_id}/review-sessions/{review_id}
POST /api/v1/courses/{course_id}/review-sessions/{review_id}/answer
POST /api/v1/courses/{course_id}/review-sessions/{review_id}/skip
```

Start with `{ "provider": "local" }` or the configured tutor provider. Answer with
`{ "student_answer": "...", "grading_provider": "local", "duration_seconds": 90 }`.
The returned practice ID also supports the existing tutor hint and solution endpoints.
Local generation requires a mapped question with a reference solution for the selected
topic; unavailable material or no due topic returns 409 without creating a partial session.

Grading uses the existing evidence-weighted practice pipeline, including hint penalties,
mastery recomputation, and history. The response includes the graded attempt and the
refreshed review priority and due state. Completion means an answer was graded, not
that the answer was correct. Revealed solutions cannot be submitted as mastery evidence.
Duplicate answers are rejected. Skipping is idempotent and never marks a topic reviewed.

Creation persists the question and review link in one transaction. A unique active
reservation prevents duplicate unfinished reviews for a topic. Each session preserves
its original selection reason and evidence timestamp for inspection later.

## Semester command center



`GET /api/v1/semester/dashboard` returns course estimates, normalized target gaps,
calendar-day deadline pressure, due review counts, queue summaries, and the next
executable study block. Supply `?queue_id=...` to select a specific queue; otherwise
it selects the newest active queue. Separate queue budgets are never added together.

Courses with no measured topics return a null grade and an `unmeasured` target status.
Partially measured courses use the existing retention-aware model and baseline for
unmeasured topics; the response includes evidence coverage and confidence. Target
status indicates an estimated gap, not a predicted probability of passing or failing.

The dashboard is read-only. Changed evidence or course settings, a new calendar day,
missing topics, or exact deadlines that no longer fit flag the queue for refresh.
Stale planned work is withheld from `next_action`; in-progress work remains visible.
Use the queue refresh endpoint to rebuild it. Saved forecasts remain available in
queue revisions, separate from the dashboard's current course estimates.

## Persistent semester control loop



StudyOS can now persist a multi-course optimization as one executable semester study
queue. The queue preserves immutable planning revisions while the current revision
supports starting, completing, and skipping blocks in strict order.

```text
POST /api/v1/semester-queues
GET  /api/v1/semester-queues
GET  /api/v1/semester-queues/{queue_id}

POST /api/v1/semester-queues/{queue_id}/blocks/{block_id}/start
POST /api/v1/semester-queues/{queue_id}/blocks/{block_id}/complete
POST /api/v1/semester-queues/{queue_id}/blocks/{block_id}/skip
POST /api/v1/semester-queues/{queue_id}/refresh
```

Actual completion time reduces the shared remaining budget. Missed time is tracked
separately. Every completion, skip, or manual budget change supersedes unfinished
blocks and runs the cross-course optimizer again with the remaining time.

Exact deadline horizons are stored as absolute timestamps, so they continue to count
down across revisions. Each revision also stores a source fingerprint for course
deadlines, targets, grade scales, and measured topic mastery. Reading an idle queue
automatically creates a `source_change` revision when those inputs have changed or an
exact deadline crosses a scheduling-block boundary. In-progress work is never
silently superseded.

Completed study contributes only a schedule-local mastery projection. New measured
mastery supersedes older projections, so executing a queue never writes synthetic
diagnostic evidence.

Each revision exposes the optimizer model, per-course forecasts and allocations,
aggregate target-gap metrics, utility, and its complete block history.

## Multi-course optimization

StudyOS can now allocate one scarce study-time budget across multiple courses with different grading scales, targets, deadlines, and evidence quality.

```text
Physics          25 / 30 target
Programming      80 / 100 target
Linear Algebra   27 / 30 target

7 hours available
        ↓
normalized target-gap utility
+ deadline pressure
+ evidence confidence
        ↓
block-by-block global competition
        ↓
ordered cross-course study schedule
```

### Multi-course endpoint

```text
POST /api/v1/multi-course-plan

POST /api/v1/semester-queues
GET  /api/v1/semester-queues/{queue_id}
POST /api/v1/semester-queues/{queue_id}/refresh
```

Example request:

```json
{
  "available_hours": 7,
  "block_minutes": 30,
  "courses": [
    {
      "course_id": "physics-id",
      "hours_until_exam": 18
    },
    {
      "course_id": "linear-id",
      "hours_until_exam": 48
    },
    {
      "course_id": "programming-id",
      "hours_until_exam": 96
    }
  ]
}
```

Each course can also override its target grade, baseline mastery, per-topic mastery, and whether stored measured mastery should be used.

### Raw marks are never compared across unrelated grade scales

A gain of `+2` marks in a 30-point course is not treated as equivalent to `+2` marks in a 100-point course.

For every candidate block, StudyOS first calculates the expected mark gain using the existing calibrated course model, then converts only the useful part of that gain into normalized target-gap reduction:

```text
raw expected mark gain
        ↓
min(raw gain, remaining target gap)
        ↓
divide by course maximum grade
        ↓
normalized target-gap reduction
```

The global utility used for allocation is:

```text
normalized target-gap reduction
× deadline multiplier
× confidence multiplier
```

This means two otherwise identical courses on 30-point and 100-point scales produce comparable normalized utility even though their raw expected mark gains differ substantially.

### Sequential global allocation

The optimizer is `normalized-target-utility-greedy-v1`.

It does not rank courses once and assign fixed chunks. After every study block it:

```text
updates projected topic mastery
        ↓
recalculates projected course grade
        ↓
recalculates remaining target gap
        ↓
reduces exact deadline horizon by elapsed global study time
        ↓
re-evaluates every eligible course
        ↓
selects the highest current utility block
```

Diminishing returns inside one course can therefore cause the next block to move to another course.

### Deadline pressure

A course request may provide exact `hours_until_exam`.

Exact deadline horizons are hard cutoffs. If only 30 minutes remain before that exam, StudyOS cannot allocate a later block to the course after those 30 minutes have elapsed in the global schedule.

Deadline pressure also increases when the estimated study hours required to reach the target consume a large share of the exact time remaining.

Course-level `exam_date` is still supported when exact hours are not provided. Because `exam_date` contains only a calendar date, it contributes **coarse urgency weighting only**. StudyOS does not invent an exam clock time.

### Evidence uncertainty

Expected study gains with weaker evidence are conservatively shrunk before courses compete globally.

Current confidence multipliers are:

```text
low      0.80
medium   0.90
high     1.00
```

This does not change stored mastery. It only prevents a poorly measured course from winning scarce global time purely because a noisy point estimate looks large.

### Targets are real stopping conditions

Once a course reaches its stated target under the planning projection, it stops receiving scarce time.

If every selected course has already reached its target, StudyOS returns the remaining time as `unallocated_hours` rather than generating fake productivity work just to fill the schedule.

The response exposes both per-course and global results:

```text
ordered cross-course blocks
next action
raw expected mark gain per block
normalized target-gap reduction
utility score
course allocation totals
current and projected grades
target gaps before / after
deadline source and multiplier
plan confidence and confidence multiplier
unallocated time
```

Expected gains and utility remain planning heuristics, not guaranteed exam results.

## Persistent Emergency Mode

Single-course Emergency Mode can persist an optimized schedule, record what actually happened, and rebuild only the unfinished portion when time or mastery changes.

```text
POST /api/v1/courses/{course_id}/emergency-plan
POST /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules
GET  /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}
```

Current-revision blocks support:

```text
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/start
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/complete
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/skip
POST /api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule
```

Every replan creates an immutable revision. Old unfinished blocks become `superseded`, while completed and skipped blocks remain historical evidence of what happened.

Actual minutes affect the remaining budget: finishing early preserves time, finishing late consumes extra time, and skipped blocks can explicitly record lost minutes.

Study completion never writes fake mastery evidence. Schedule-local learning projections are replaced by newer diagnostic or practice evidence whenever it exists.

## Planning and grade modelling

The normal `heuristic-v5` planner combines course importance, exam weight, effective mastery, mistake burden, personalized learning scale, and calibrated retention.

The single-course Emergency Mode optimizer `expected-marks-greedy-v1` assigns each study block to the topic with the highest current expected marginal mark gain.

The `probabilistic-v1` layer adds score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Immutable pre-exam forecasts can later receive real outcomes. StudyOS measures prediction error, interval coverage, Brier score, and log loss; guarded empirical recalibration is evaluated with rolling-origin held-out validation.

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

POST /api/v1/multi-course-plan

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
- [x] normalized multi-course optimization

### Phase 6 — Study operating system
- [x] persistent semester-wide study queue
- [x] semester command-center API
- [x] spaced-repetition workflow
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

The next milestone is **source-grounded cheat-sheet generation**: compile course
formulas, methods, and recurring mistakes into a compact exam reference with citations.
