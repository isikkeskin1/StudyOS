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
- Can the tutor explain from my actual course files with exact citations?
- Can StudyOS create, grade, and adapt practice without revealing solutions too early?
- Can the tutor remember recurring mistakes and change how it teaches?
- What should I deprioritize when time is running out?

## Current milestone — persistent incremental embedding index

The backend is now at **v0.24.0**.

Semantic retrieval no longer needs to recompute unchanged course-chunk embeddings on every tutor request. StudyOS now persists chunk vectors and reuses them across search, tutor, and grounded practice retrieval.

```text
processed course chunks
        ↓
provider + model + exact content hash
        ↓
TutorChunkEmbedding
        ↓
reusable chunk vectors
        ↓
semantic / hybrid reranking
```

The query itself is still embedded for each request. Only the comparatively expensive repeated source-chunk work is cached.

### Strict cache identity and invalidation

An embedding is reusable only when all of the following still match:

```text
chunk ID
+ SHA-256 of exact chunk text
+ embedding provider
+ embedding model
```

Changing the chunk text makes that row stale. Reprocessing a document creates new chunks, which appear as missing while old rows become orphaned. Switching embedding model or provider uses a separate cache namespace instead of silently reusing incompatible vectors.

This keeps invalidation deterministic rather than relying on timestamps or fuzzy content comparisons.

### Lazy indexing and explicit full-course sync

StudyOS supports both paths:

```text
normal semantic request
        ↓
select candidate chunks
        ↓
reuse current cached vectors
        ↓
embed only missing/stale candidates
```

and:

```text
explicit index sync
        ↓
scan all processed course chunks
        ↓
embed only missing/stale chunks
        ↓
remove orphan rows
        ↓
ready index
```

A fully synced course therefore typically needs only the query-vector provider call during later semantic searches.

### Index observability

New endpoints:

```text
GET  /api/v1/courses/{course_id}/tutor/embedding-index
POST /api/v1/courses/{course_id}/tutor/embedding-index/sync
```

The status endpoint reports:

```text
status: disabled | empty | stale | ready
provider_name
model_name
total_chunks
indexed_chunks
missing_chunks
stale_chunks
orphaned_embeddings
coverage
dimensions
```

A sync response additionally reports:

```text
embedded_now
reused_chunks
deleted_orphans
```

`force=true` can rebuild every current course chunk. Sync also accepts an optional batch-size override.

### Storage boundary

Vectors are currently stored as JSON in SQLite. That is intentional.

This milestone provides **persistent embedding storage, deterministic invalidation, incremental indexing, and a stable service boundary**. It does not claim that SQLite JSON scanning is an approximate-nearest-neighbor index or a production vector database.

A later ANN/vector backend can replace the storage/search implementation behind the same retrieval interface without changing tutor behavior.

Semantic retrieval keeps the existing model names:

```text
semantic-vector-rerank-v1
hybrid-vector-bm25-v1
```

and adds `persistent_embedding_cache` to the reported retrieval components when the cache-backed semantic path is used.

## Adaptive tutor stack

### Grounded retrieval and synthesis

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval signals include BM25, course-topic evidence, embedding cosine similarity, and the persistent embedding cache.

The OpenAI synthesis provider receives only selected course-source excerpts. Every substantive answer claim must include source markers, and a local `citation-overlap-v2` validator checks that cited evidence actually supports the claim before the answer is returned.

Optional embedding configuration:

```text
STUDYOS_TUTOR_EMBEDDING_PROVIDER=none
STUDYOS_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
STUDYOS_TUTOR_EMBEDDING_MAX_CANDIDATES=128
STUDYOS_TUTOR_EMBEDDING_BATCH_SIZE=64
```

With the embedding provider set to `none`, offline BM25/topic retrieval remains fully available and explicit semantic requests fail clearly rather than pretending lexical search is semantic search.

### Guided practice and grading

StudyOS can create persisted exam-style practice, reveal three progressive hints, hide the full solution until requested, and grade free responses.

Practice evaluation supports:

```text
grading_provider: auto | local | openai
```

The rubric-aware OpenAI grader can award method credit for equivalent reasoning. Its structured rubric is locally validated before any score affects mastery. Offline deterministic grading remains available for CI and local use.

Correctness and mastery evidence are separate: hints do not make a correct answer wrong, but they reduce how strongly that attempt updates mastery. Revealing the full solution makes that item ineligible as scored mastery evidence.

### Session memory and remediation teaching

Multi-question practice sessions use the latest five completed attempts to adapt topic, difficulty, and teaching style.

```text
recent scores
+ hint use
+ recurring mistake categories
+ topic-specific error burden
        ↓
next topic / difficulty
+ teaching intro
+ mistake-specific coaching
```

Repeated sign mistakes can trigger axis/direction coaching; unit errors trigger dimensional checks; formula-selection errors force target-variable and governing-relation setup before substitution.

Teaching plans are persisted as auditable snapshots, so later attempts do not silently rewrite what the student was shown on an earlier question.

## Intelligence stack

### Course intelligence

- PDF, DOCX, PPTX, TXT, and Markdown upload/deduplication
- page/slide-aware extraction and deterministic chunking
- document classification
- course topic graph and source evidence
- past-paper question/mark extraction
- topic frequency and normalized exam weighting

### Diagnostics and mastery

- adaptive diagnostics from real past-paper questions
- persistent Bayesian mastery and confidence
- deterministic and rubric-aware grading
- mistake taxonomy and recurring mistake analytics
- response-level mastery history and trends
- forgetting-aware effective mastery
- personalized learning responsiveness and retention calibration
- exam-aware review queue
- practice evidence integrated into the same mastery model

### Planning and grade modelling

The `heuristic-v5` planner combines course importance, exam weight, effective mastery, mistakes, personalized learning scale, and calibrated retention.

The `probabilistic-v1` layer adds expected score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Immutable pre-exam forecasts can later receive real outcomes. StudyOS measures prediction error, interval coverage, Brier score, and log loss; guarded empirical recalibration is evaluated using rolling-origin held-out validation.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload course material |
| `POST` | `/api/v1/courses/{course_id}/documents/{document_id}/process` | Extract/classify/chunk material |
| `POST` | `/api/v1/courses/{course_id}/analyze` | Build course intelligence |
| `POST` | `/api/v1/courses/{course_id}/exam-intelligence/analyze` | Analyze past papers |
| `POST` | `/api/v1/courses/{course_id}/diagnostics` | Start adaptive diagnostic |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read mastery |
| `GET` | `/api/v1/courses/{course_id}/mastery/history` | Read mastery history/trends |
| `GET` | `/api/v1/courses/{course_id}/calibration` | Read learning/retention calibration |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read mistake analytics |
| `GET` | `/api/v1/courses/{course_id}/reviews` | Read review queue |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Build study plan |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast` | Raw probabilistic forecast |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast/calibrated` | Raw + empirical forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-calibration` | Historical forecast metrics |
| `GET` | `/api/v1/courses/{course_id}/forecast-validation` | Held-out model validation |
| `POST` | `/api/v1/courses/{course_id}/tutor/search` | Search grounded course evidence |
| `POST` | `/api/v1/courses/{course_id}/tutor/ask` | Produce validated grounded answer |
| `GET` | `/api/v1/courses/{course_id}/tutor/embedding-index` | Inspect embedding-index health |
| `POST` | `/api/v1/courses/{course_id}/tutor/embedding-index/sync` | Incrementally sync course vectors |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice` | Create grounded practice |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice-sessions` | Start adaptive practice session |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}` | Read session state |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}/teaching` | Read/materialize teaching plan |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate` | Grade and adapt practice |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/solution` | Reveal grounded solution |

FastAPI exposes interactive API docs at `/docs` while the server is running.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] source-aware document pipeline
- [x] topic intelligence and past-paper weighting
- [x] first study planner

### Phase 2 — Diagnostics and mastery
- [x] adaptive diagnostics and persistent mastery
- [x] mistake intelligence and answer evidence
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
- [x] grounded synthesis provider + local citation validation
- [x] optional embedding semantic reranking
- [x] persisted exam-style practice and progressive hints
- [x] adaptive practice evaluation and rubric grading
- [x] multi-question session memory and remediation teaching
- [x] persistent SQLite embedding cache
- [x] incremental/lazy chunk indexing and index-health API
- [ ] stronger entailment verifier / claim decomposition
- [ ] external vector/ANN backend

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

Planned infrastructure includes PostgreSQL, Redis/background workers, an external ANN/vector backend when scale justifies it, Docker, and a Next.js/TypeScript client.

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

The next Phase 4 quality milestone is **stronger entailment verification and claim decomposition**: move beyond lexical claim/source overlap so a fluent answer cannot pass validation merely because it shares several words with the cited excerpt.