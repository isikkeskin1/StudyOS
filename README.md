# StudyOS

StudyOS is an evidence-driven academic operating system that turns uploaded course material and student performance into adaptive study plans, mastery estimates, grade forecasts, and source-grounded tutoring.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## Current milestone — retrieval hard-negative benchmarking

The backend is now at **v0.26.0**.

StudyOS can now measure retrieval quality instead of assuming that adding embeddings automatically improves the tutor. A labeled benchmark runs the same queries against multiple ranking strategies and reports where each one succeeds or fails.

```text
labeled query
+ correct course chunk IDs
        ↓
retrieval-hard-negative-v1
        ↓
BM25 baseline
Topic-aware BM25
Semantic reranking
Hybrid reranking
        ↓
Top-1 accuracy
Hit rate @ K
Recall @ K
MRR
Mean first-relevant rank
Failure cases
```

### Same cases, same labels

New endpoint:

```text
POST /api/v1/courses/{course_id}/tutor/retrieval-benchmark
```

A benchmark case contains a stable case ID, a human-readable label, the query, and one or more chunk IDs judged relevant:

```json
{
  "case_id": "acceleration-direction",
  "label": "paraphrased direction relation",
  "query": "Which way does acceleration point relative to net force?",
  "relevant_chunk_ids": ["<chunk-id>"]
}
```

StudyOS validates that every labeled chunk is a processed member of that course, preventing cross-course or stale labels from silently corrupting metrics.

### Comparable ranking modes

The benchmark supports:

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

These weights mirror the current tutor-ranking behavior. The benchmark therefore measures the implementation StudyOS actually uses rather than an unrelated offline scoring script.

If embeddings are not configured, BM25/topic modes still run and semantic/hybrid are returned as `unavailable` instead of failing the whole benchmark.

### Metrics and hard-negative failures

For every evaluated mode StudyOS reports:

```text
top1_accuracy
hit_rate_at_k
recall_at_k
mean_reciprocal_rank
mean_first_relevant_rank
```

Per-case output includes the ranked chunks and their lexical, semantic, topic, and final scores. Every top-1 miss is surfaced with the top-ranked distractor; cases that do not retrieve any relevant chunk inside K are explicitly marked `missed_at_k`.

The response also names the best evaluated mode using MRR first, followed by top-1 accuracy, recall@K, and hit-rate@K as tie breakers. That label is descriptive for the supplied benchmark only; it is not treated as proof that one retrieval strategy is globally superior.

A regression fixture includes a deliberately keyword-heavy distractor and a semantically correct paraphrase, proving that the harness can detect a lexical failure that semantic retrieval recovers.

## Tutor grounding and retrieval

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval signals include BM25, course-topic evidence, embedding cosine similarity, and a persistent chunk-vector cache.

Semantic vectors are persisted in SQLite with strict identity:

```text
chunk ID
+ SHA-256(exact chunk text)
+ embedding provider
+ embedding model
```

Normal tutor requests lazily embed only missing/stale candidate chunks. Full-course maintenance is available through:

```text
GET  /api/v1/courses/{course_id}/tutor/embedding-index
POST /api/v1/courses/{course_id}/tutor/embedding-index/sync
```

Vectors are currently JSON in SQLite. This is a persistent reranking cache, not an ANN/vector database.

### Atomic grounding validation

Generated tutor prose is decomposed into atomic factual claims before it can be returned:

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

The deterministic validator catches explicit reversals such as same/opposite direction, positive/negative, greater/less, increase/decrease, direct/inverse proportionality, clockwise/counterclockwise, upward/downward, and negation mismatches. Numerical claims must also agree with cited evidence within a small rounding tolerance.

This is deliberately described as a conservative local entailment gate, not a learned NLI model.

## Adaptive practice

StudyOS can create persisted exam-style practice, keep solutions hidden, reveal three progressive hints, and grade free responses.

Practice evaluation supports deterministic local grading and rubric-aware OpenAI grading. Scores, mistake categories, hint usage, duration, and grader confidence feed the same mastery/history/mistake model used by diagnostics.

Multi-question practice sessions remember recent scores, hint dependence, recurring mistakes, and topic-specific error burden. Session teaching can adapt both the next question and the solving process—for example, repeated sign mistakes can force axis/direction setup before substitution while unit mistakes trigger explicit dimensional checks.

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
- [ ] persisted benchmark datasets / benchmark history
- [ ] external ANN/vector backend when benchmarked scale justifies it

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

The next tutor-quality milestone is **persisted benchmark datasets and benchmark history**: turn one-off labeled evaluations into reusable course-level regression suites so retrieval changes can be compared against prior benchmark runs before they ship.
