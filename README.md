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
- Can a cited tutor answer be rejected when the citation does not actually support the claim?
- What should I deprioritize when time is running out?

## Current milestone — atomic claim entailment validation

The backend is now at **v0.25.0**.

Tutor grounding no longer treats a whole sentence as one lexical-overlap blob. StudyOS first decomposes generated prose into atomic factual claims, inherits the sentence citations for each independent clause, and validates every atomic claim before the answer can be returned.

```text
generated tutor answer
        ↓
sentence boundaries
        ↓
atomic-claims-v1
        ↓
independent factual claims
        ↓
citation validity
+ contradiction checks
+ numerical consistency
+ strict content coverage
        ↓
atomic-entailment-v1
        ↓
all claims pass → answer
any claim fails → reject entire draft
```

This is intentionally a deterministic, fail-closed validator. StudyOS does **not** label it as a learned NLI model or pretend lexical heuristics provide perfect semantic entailment.

### Atomic claim decomposition

A sentence such as:

```text
Net force equals mass times acceleration and acceleration points
in the same direction as the net force [1].
```

is evaluated as two claims:

```text
1. Net force equals mass times acceleration.          citation [1]
2. Acceleration points in the same direction...      citation [1]
```

Independent clauses joined by `and`, `but`, `whereas`, `however`, or semicolons can therefore fail separately instead of one supported half masking an unsupported half.

The OpenAI synthesis prompt also asks the model to keep substantive sentences atomic where possible and forbids adding scientific facts, qualifiers, numbers, causal relationships, or exceptions that are absent from the supplied excerpts.

### Contradiction-aware checks

High word overlap is no longer sufficient.

For example, this source:

```text
Acceleration points in the same direction as the net force.
```

does not support:

```text
Acceleration points in the opposite direction as the net force [1].
```

even though almost every word overlaps.

The local contradiction gate currently recognizes explicit polarity reversals including:

```text
same direction ↔ opposite direction
positive ↔ negative
greater than ↔ less than
increase ↔ decrease
directly proportional ↔ inversely proportional
clockwise ↔ counterclockwise
upward ↔ downward
```

It separately checks negation polarity, so:

```text
Momentum is conserved in an isolated system.
```

cannot support:

```text
Momentum is not conserved in an isolated system [1].
```

### Unsupported additions

The validator canonicalizes a conservative set of grammatical/paraphrase variants such as:

```text
equals ↔ equal
times ↔ multiplied
resultant ↔ net
fixed ↔ constant
points ↔ directed
```

but substantive new content still fails closed.

For example:

```text
Source:
Net force equals mass times acceleration.

Draft:
Net force equals mass times quantum acceleration [1].
```

is rejected even though its lexical overlap is very high.

This intentionally favors source-faithful answers over fluent extrapolation.

### Numerical consistency

Numerical assertions must also occur in the cited evidence.

A small relative tolerance allows ordinary rounding:

```text
source: 9.81
claim:  9.8      → accepted
```

while a materially different value is rejected:

```text
source: 9.81
claim:  10       → rejected
```

### Tutor response contract

The public `/tutor/ask` shape remains backward-compatible.

`validated_claim_count` and `unsupported_claim_count` now count **atomic claims**, `validation_model` reports:

```text
atomic-entailment-v1
```

and the default minimum local support threshold is now `0.35`.

Internally the validator additionally tracks:

```text
atomic claim count
contradicted claims
unsupported additions
numeric mismatches
invalid citations
claim decomposition model
```

The full generated answer is still discarded if any substantive atomic claim fails.

## Adaptive tutor stack

### Grounded retrieval and synthesis

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval signals include BM25, course-topic evidence, embedding cosine similarity, and the persistent embedding cache.

The OpenAI synthesis provider receives only selected course-source excerpts. Source contents are treated as untrusted data and are never allowed to become tutor instructions.

After synthesis, `atomic-claims-v1` + `atomic-entailment-v1` locally validate every substantive claim before the answer is returned.

Optional embedding configuration:

```text
STUDYOS_TUTOR_EMBEDDING_PROVIDER=none
STUDYOS_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
STUDYOS_TUTOR_EMBEDDING_MAX_CANDIDATES=128
STUDYOS_TUTOR_EMBEDDING_BATCH_SIZE=64
```

With the embedding provider set to `none`, offline BM25/topic retrieval remains fully available and explicit semantic requests fail clearly rather than pretending lexical search is semantic search.

### Persistent incremental embedding index

Semantic retrieval persists course-chunk vectors instead of recomputing unchanged source embeddings on every request.

A cache row is reusable only when these all match:

```text
chunk ID
+ SHA-256 of exact chunk text
+ embedding provider
+ embedding model
```

Normal semantic requests lazily embed only missing/stale candidate chunks. Full-course maintenance is available through:

```text
GET  /api/v1/courses/{course_id}/tutor/embedding-index
POST /api/v1/courses/{course_id}/tutor/embedding-index/sync
```

Index health reports `disabled | empty | stale | ready`, coverage, missing/stale chunks, dimensions, and orphaned rows.

Vectors are currently JSON in SQLite. This provides persistence, deterministic invalidation, incremental reuse, and a stable storage boundary; it is not presented as an ANN/vector database.

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
| `POST` | `/api/v1/courses/{course_id}/tutor/ask` | Produce atomic-claim validated answer |
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
- [x] atomic claim decomposition and contradiction-aware entailment gate
- [ ] retrieval-quality benchmark / hard-negative evaluation
- [ ] external vector/ANN backend when scale justifies it

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

The next tutor-quality milestone is a **retrieval hard-negative benchmark**: measure whether BM25/topic/semantic ranking actually selects the correct course evidence under paraphrases, distractor chunks, near-duplicate formulas, and misleading high-overlap material before choosing any external vector backend.
