# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, and source-grounded tutoring.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## Current milestone — persisted retrieval benchmark regression suites

The backend is now at **v0.27.0**.

Retrieval evaluation is no longer a one-off request. StudyOS can persist an immutable labeled benchmark suite, run it repeatedly after retrieval changes, retain every result, and compare the current run with an earlier comparable baseline.

```text
immutable labeled suite
        ↓
BM25 / topic / semantic / hybrid
        ↓
run snapshot
        ↓
Top-1 / Hit@K / Recall@K / MRR
        ↓
compare with previous same-K run
        ↓
PASS | REGRESSION | NO_BASELINE
```

### Persisted suites

Create and inspect reusable course-level datasets through:

```text
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites
GET  /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites
GET  /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}
```

A suite snapshots:

```text
name / description
labeled queries
relevant chunk IDs
default retrieval modes
default K / max results
creation time
```

Suites are intentionally immutable. If the dataset changes, create another suite instead of silently rewriting the benchmark that produced older results.

Chunk labels remain strict. If document reprocessing deletes/replaces a labeled chunk, the next suite run fails closed as stale rather than quietly evaluating a different source.

### Run history and regression comparison

Run and inspect a suite through:

```text
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs
GET  /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs
GET  /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs/{run_id}
```

Each run persists the full benchmark result plus:

```text
revision label
retrieval modes
K / max results
best mode
baseline run ID
metric deltas
regressed metrics
regression verdict
```

By default the baseline is the most recent prior run of the same suite with the same `k`. A specific baseline run can also be requested, but it must belong to that suite and use the same `k`.

The regression gate watches bounded ranking metrics:

```text
top1_accuracy
hit_rate_at_k
recall_at_k
mean_reciprocal_rank
```

A configurable tolerance defaults to `0.02`. If any comparable mode drops beyond that tolerance, the run is marked `regression`. Mean first-relevant rank is still reported as a diagnostic delta, but it is not used by the initial gate because its scale is not bounded like the other metrics.

History endpoints return compact summaries; the large per-case ranked payload is only returned when an individual run is fetched.

## Retrieval hard-negative benchmarking

The underlying benchmark remains available directly through:

```text
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark
```

All evaluated modes use the same labeled queries and relevant chunk IDs.

Current ranking modes:

```text
bm25
    pure lexical baseline

topic
    0.78 lexical + 0.22 course-topic affinity

semantic
    0.90 embedding cosine + 0.10 topic affinity

hybrid
    0.50 lexical + 0.35 semantic + 0.15 topic affinity
```

Metrics include Top-1 accuracy, Hit@K, Recall@K, mean reciprocal rank, mean first-relevant rank, and explicit hard-negative failures. Semantic/hybrid modes are reported as unavailable when embeddings are disabled while lexical baselines still run.

## Tutor grounding and retrieval

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval signals include BM25, course-topic evidence, embedding cosine similarity, and a persistent chunk-vector cache.

Semantic vectors are persisted in SQLite using strict cache identity:

```text
chunk ID
+ SHA-256(exact chunk text)
+ embedding provider
+ embedding model
```

Normal requests lazily embed missing/stale candidates. Full-course maintenance is available through:

```text
GET  /api/v1/courses/{course_id}/tutor/embedding-index
POST /api/v1/courses/{course_id}/tutor/embedding-index/sync
```

Vectors are currently JSON in SQLite. This is a persistent reranking cache, not an ANN/vector database.

### Atomic grounding validation

Generated tutor prose is decomposed into atomic claims and validated locally before return:

```text
generated answer
        ↓
atomic-claims-v1
        ↓
citation validity
+ contradiction checks
+ numerical consistency
+ strict content coverage
        ↓
atomic-entailment-v1
        ↓
all claims pass → answer
any claim fails → discard draft
```

The deterministic gate catches explicit polarity/direction reversals, negation mismatches, unsupported additions, and materially different numerical claims. It is intentionally described as a conservative local validator, not a learned NLI model.

## Adaptive practice

StudyOS can create persisted exam-style practice, keep solutions hidden, reveal three progressive hints, and grade free responses.

Practice evaluation supports deterministic local grading and rubric-aware OpenAI grading. Scores, mistake categories, hint usage, duration, and grader confidence feed the same mastery/history/mistake model used by diagnostics.

Multi-question sessions remember recent scores, hint dependence, recurring mistakes, and topic-specific error burden. Session teaching can adapt both the next question and the solving process.

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

### Planning and grade modelling

The `heuristic-v5` planner combines course importance, exam weight, effective mastery, mistakes, personalized learning scale, and calibrated retention.

The `probabilistic-v1` layer adds score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Immutable pre-exam forecasts can later receive real outcomes. StudyOS measures prediction error, interval coverage, Brier score, and log loss; guarded empirical recalibration is evaluated with rolling-origin held-out validation.

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
POST /api/v1/courses/{course_id}/grade-forecast
POST /api/v1/courses/{course_id}/grade-forecast/calibrated
GET  /api/v1/courses/{course_id}/forecast-calibration
GET  /api/v1/courses/{course_id}/forecast-validation

POST /api/v1/courses/{course_id}/tutor/search
POST /api/v1/courses/{course_id}/tutor/ask
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs
GET  /api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs
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
- [x] course-isolated BM25/topic retrieval
- [x] exact page/slide/document citations
- [x] grounded synthesis + local validation
- [x] semantic reranking and persistent embedding cache
- [x] adaptive practice, rubric grading, session memory, remediation teaching
- [x] atomic claim decomposition and contradiction-aware entailment
- [x] retrieval hard-negative benchmark and comparative metrics
- [x] persisted benchmark suites, run history, and regression verdicts
- [ ] external ANN/vector backend only when benchmarked scale justifies it

### Phase 5 — Optimization
- [ ] expected marks per study hour
- [ ] emergency mode
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

The next product milestone is **Phase 5 expected marks per study hour + Emergency Mode**: use the existing exam weights, mastery, personalized learning curves, forgetting, and grade forecast to rank where each remaining hour buys the most expected marks, then explicitly surface low-value topics to skip when time is short.
