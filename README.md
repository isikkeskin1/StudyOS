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
- Can the tutor explain from my actual course files with exact citations?
- Can StudyOS create, grade, and adapt practice without revealing solutions too early?
- What should I deprioritize when time is running out?

## Current milestone — rubric-aware free-response grading

The backend is now at **v0.21.0**.

Practice evaluation can use:

```text
grading_provider: auto | local | openai
```

`auto` prefers the rubric-aware OpenAI grader when `OPENAI_API_KEY` is configured and otherwise uses the deterministic local grader. Explicit `openai` requests fail with `503` when the provider is not configured.

### Rubric-aware grading

The OpenAI grading adapter receives only:

```text
question
reference solution
student answer
mark total
```

It is instructed to accept mathematically or scientifically equivalent methods, award method credit where justified, and classify concrete mistake types instead of requiring lexical overlap with the reference solution.

The grader returns a structured rubric such as:

```text
Criterion                         Awarded
------------------------------------------------
Correct governing principle       2.0 / 2.0
Equation setup                     2.0 / 2.0
Algebra / substitution             1.5 / 2.0
Final value and units              1.0 / 2.0

Total                              6.5 / 8.0
```

StudyOS does **not** trust those totals blindly. It locally verifies that:

- criterion maximums sum exactly to the item's mark total,
- awarded marks are inside each criterion's allowed range,
- confidence is in `[0, 1]`,
- mistake categories use the StudyOS taxonomy,
- duplicate mistake categories are collapsed to the strongest evidence,
- the final normalized score is recomputed locally from criterion marks.

Malformed rubric output is rejected rather than normalized into a plausible-looking score.

Every evaluated practice attempt persists an auditable grading artifact with the grading mode, provider, criteria, awarded marks, and total marks.

### Local fallback

Offline/CI evaluation remains available as:

```text
deterministic-reference-v1
```

It preserves the existing lexical, numerical, and unit-based grader. This is intentionally provisional for explanation-heavy or derivation-heavy answers but gives StudyOS a deterministic fallback and regression baseline.

## Adaptive practice loop

Practice now forms one continuous learning loop:

```text
weakness / requested topic
        ↓
grounded practice question
        ↓
progressive hints
        ↓
student answer
        ↓
rubric-aware or deterministic grading
        ↓
score + feedback + mistake categories
        ↓
hint-aware mastery evidence
        ↓
mastery/history/mistake update
        ↓
adaptive next question
```

Correctness and mastery evidence are deliberately separate. Hints do not make a correct answer "wrong"; instead they reduce how strongly the attempt updates mastery. Once the full solution is revealed, that item is no longer accepted as mastery evidence.

The adaptive follow-up policy can return:

```text
reinforce
maintain
increase_difficulty
reoptimize
```

Strong unassisted performance can raise difficulty or move to the next weakness. Weak or heavily hinted performance keeps the student on the same topic and may lower difficulty.

## Grounded tutor retrieval and synthesis

Tutor requests support:

```text
retrieval_mode: auto | lexical | semantic | hybrid
provider: auto | local | openai
```

Current retrieval models include:

```text
lexical-bm25-v1
hybrid-topic-bm25-v1
semantic-vector-rerank-v1
hybrid-vector-bm25-v1
```

The OpenAI synthesis provider receives only selected course-source excerpts. Every substantive answer claim must include source markers, and a local `citation-overlap-v2` validator checks that cited evidence actually overlaps the claim before an answer is returned.

Optional embedding configuration:

```text
STUDYOS_TUTOR_EMBEDDING_PROVIDER=none
STUDYOS_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
STUDYOS_TUTOR_EMBEDDING_MAX_CANDIDATES=128
```

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
- answer capture and solution-grounded grading
- mistake taxonomy and recurring mistake analytics
- response-level mastery history and trends
- forgetting-aware effective mastery
- personalized learning responsiveness and retention calibration
- exam-aware review queue
- practice attempts integrated into the same mastery and mistake model

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
| `POST` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate` | Grade response and adapt next practice |
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
- [x] deterministic solution-grounded grading
- [x] rubric-aware LLM grading adapter

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
- [x] adaptive practice evaluation
- [x] rubric-aware free-response grading
- [ ] persistent embedding index / vector database
- [ ] stronger entailment verifier
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

The next Phase 4 milestone is **practice-session memory and personalized remediation**: carry recent attempts, recurring mistake patterns, and unresolved concepts across a multi-question tutor session so the next question and explanation respond to more than a single score.
