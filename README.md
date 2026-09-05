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
- Are StudyOS forecasts accurate against real outcomes?
- Can the tutor explain from my actual lectures, notes, exams, and solutions with exact citations?
- Can StudyOS generate grounded practice and reveal help progressively instead of dumping the solution?
- What should I deprioritize when time is running out?

## Current milestone — semantic retrieval and guided practice

The backend is now at **v0.19.0**.

The course-aware tutor now supports four retrieval modes:

```text
auto
lexical
semantic
hybrid
```

The default deployment remains offline-safe. With no embedding provider configured, `auto` preserves the existing BM25 + course-topic retrieval path. When embeddings are enabled, `auto` can add vector similarity as a reranking signal.

Current retrieval models include:

```text
lexical-bm25-v1
hybrid-topic-bm25-v1
semantic-vector-rerank-v1
hybrid-vector-bm25-v1
```

Each citation can expose lexical, semantic, and course-topic scores independently so retrieval remains inspectable.

### Optional embedding provider

The first external embedding adapter uses the OpenAI embeddings API and defaults to:

```text
text-embedding-3-small
```

Configuration:

```text
STUDYOS_TUTOR_EMBEDDING_PROVIDER=none
STUDYOS_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
STUDYOS_TUTOR_EMBEDDING_MAX_CANDIDATES=128
```

Explicit `semantic` or `hybrid` requests fail with `503` when no embedding provider is configured instead of silently pretending lexical retrieval is semantic retrieval.

## Grounded tutor synthesis

`POST /api/v1/courses/{course_id}/tutor/ask` still supports:

```text
provider: auto | local | openai
```

The synthesis flow remains:

```text
question
   ↓
course-isolated retrieval
   ↓
ranked citation packet
   ↓
local provider OR OpenAI provider
   ↓
local citation-overlap-v2 validation
   ↓
supported answer OR refusal
```

The OpenAI provider receives only the selected citation packet, has no web tools enabled, treats source excerpts as untrusted data, and uses `store=False`. Every substantive answer sentence must contain valid source markers such as `[1]`.

## Guided practice

StudyOS now has persisted practice items with hidden solutions and progressive hints.

### Create practice

```text
POST /api/v1/courses/{course_id}/tutor/practice
```

Example:

```json
{
  "difficulty": "medium",
  "provider": "local"
}
```

When no topic is specified, StudyOS chooses a topic using exam importance, measured mastery, and mastery confidence. The local provider does **not** invent synthetic questions: it reuses a mapped past-paper question only when an extracted reference solution exists.

Local generation is labelled:

```text
generation_provider: local-past-exam-v1
generation_mode: past-exam-reuse-v1
```

When `provider: openai` is configured, StudyOS can create a novel exam-style item from retrieved course evidence. The generated solution must pass the same local claim-to-citation validator before the item is saved.

### Progressive hints

```text
POST /api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint
```

Each request reveals exactly the next hint. The initial create response contains no hints and no solution text. After all three hints are exhausted, the endpoint returns `409` rather than looping or skipping state.

### Reveal solution

```text
GET /api/v1/courses/{course_id}/tutor/practice/{practice_id}/solution
```

The solution is stored separately from the initial question response and is returned with its source references only when requested.

## Existing intelligence stack

### Course intelligence

- upload/deduplication for PDF, DOCX, PPTX, TXT, and Markdown
- source-aware extraction with PDF page and PowerPoint slide references
- document classification and chunking
- course topic graph, source evidence, and topic relationships
- past-paper question/mark extraction
- topic frequency and normalized exam weighting

### Diagnostics and mastery

- adaptive diagnostics from real past-paper questions
- persistent Bayesian topic mastery and confidence
- answer capture and solution-grounded deterministic grading
- mistake taxonomy and recurring mistake analytics
- response-level mastery history and trends
- forgetting-aware effective mastery
- personalized learning responsiveness and retention calibration
- exam-aware review queue

### Planning and grade modelling

The `heuristic-v5` planner combines course importance, exam weight, forgetting-adjusted mastery, mistakes, personalized learning scale, and calibrated retention.

The `probabilistic-v1` layer adds expected score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Forecast snapshots can later receive real exam outcomes. StudyOS measures MAE, RMSE, bias, interval coverage, Brier score, and log loss, applies guarded `empirical-v1` recalibration only after enough outcomes exist, and evaluates it with rolling-origin held-out validation.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create a course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload material |
| `POST` | `/api/v1/courses/{course_id}/documents/{document_id}/process` | Extract/classify material |
| `POST` | `/api/v1/courses/{course_id}/analyze` | Build course intelligence |
| `POST` | `/api/v1/courses/{course_id}/exam-intelligence/analyze` | Analyze past papers |
| `POST` | `/api/v1/courses/{course_id}/diagnostics` | Start adaptive diagnostic |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/responses` | Score/store response |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/grade` | Auto-grade from extracted solution |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read mastery |
| `GET` | `/api/v1/courses/{course_id}/mastery/history` | Read mastery history/trends |
| `GET` | `/api/v1/courses/{course_id}/calibration` | Read learning/retention calibration |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read mistake analytics |
| `GET` | `/api/v1/courses/{course_id}/reviews` | Read review queue |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Build study plan |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast` | Raw probabilistic forecast |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast/calibrated` | Raw + empirical forecast |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots` | Save pre-exam forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-calibration` | Historical forecast metrics |
| `GET` | `/api/v1/courses/{course_id}/forecast-validation` | Held-out model validation |
| `POST` | `/api/v1/courses/{course_id}/tutor/search` | Search grounded course evidence |
| `POST` | `/api/v1/courses/{course_id}/tutor/ask` | Produce validated grounded answer |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice` | Create grounded practice |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint` | Reveal next hint |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/solution` | Reveal solution + sources |

FastAPI exposes interactive API docs at `/docs` while the server is running.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] source-aware document pipeline
- [x] topic intelligence and past-paper weighting
- [x] first study planner

### Phase 2 — Diagnostics and mastery
- [x] adaptive diagnostics and persistent mastery
- [x] mistakes and answer evidence
- [x] forgetting-aware reviews
- [x] mastery history and personalized learning/retention calibration
- [ ] richer rubric/LLM grading adapter

### Phase 3 — Grade modelling
- [x] probabilistic score distributions and target probabilities
- [x] immutable forecasts and real outcomes
- [x] empirical calibration/recalibration
- [x] reliability curves and rolling held-out validation

### Phase 4 — Course-aware tutor
- [x] deterministic course-isolated BM25 retrieval
- [x] exact page/slide/document citations
- [x] course topic/evidence retrieval signal
- [x] external grounded synthesis provider
- [x] local claim-to-citation validation
- [x] optional embedding/vector retrieval adapter
- [x] persisted exam-style practice items
- [x] progressive hint and solution reveal
- [ ] persistent embedding index / vector database
- [ ] stronger sentence-level entailment verifier
- [ ] adaptive difficulty from response history
- [ ] tutor conversation/session memory
- [ ] richer personalization from mistake state

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

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, SQLite, pypdf, python-docx, python-pptx, OpenAI SDK, Pytest, Ruff, and GitHub Actions.

Planned infrastructure includes PostgreSQL, Redis/background workers, a persistent vector index, Docker, and a Next.js/TypeScript client.

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

The next Phase 4 milestone is **adaptive practice evaluation**: grade a practice response, update mastery/mistakes from it, and automatically choose the next question difficulty and topic from the student's performance.
