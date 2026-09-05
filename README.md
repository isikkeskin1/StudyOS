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
- Can the tutor remember recurring mistakes across several questions instead of reacting to one score?
- Can the tutor change how it teaches when the same error pattern keeps appearing?
- What should I deprioritize when time is running out?

## Current milestone — session-aware remediation teaching

The backend is now at **v0.23.0**.

Practice sessions can now change **how** StudyOS teaches, not only which question it chooses next. For the current unanswered session item, StudyOS snapshots the recent learning context and produces a deterministic teaching plan:

```text
last five completed attempts
+ scores
+ hint usage
+ recurring mistake categories
+ topic carrying the mistake burden
        ↓
deterministic-session-remediation-v1
        ↓
teaching intro
+ three coaching steps
        ↓
normal hidden course hint
```

The course hint and solution remain unchanged and hidden until explicitly revealed. Remediation changes the student's solving process rather than leaking the answer.

### Mistake-specific coaching

If a mistake category repeats at least twice in the recent session window, StudyOS switches to `remediate_pattern` and uses category-specific process coaching. Current patterns include:

```text
concept
formula_selection
algebra
arithmetic
sign
units
interpretation
incomplete_reasoning
careless
other
```

For example, repeated `sign` mistakes produce guidance such as:

```text
1. Choose and write the positive axis.
2. Mark each relevant direction relative to that axis.
3. Substitute signed quantities only after the symbolic relationship is correct.
```

Repeated `units` mistakes instead make the student annotate every quantity with units, convert to a consistent system, and check final dimensions. Formula-selection errors make the student identify the target variable and governing relation before substituting numbers.

The remediation category is not hard-coded by topic. StudyOS uses whichever mistake evidence actually dominates the recent attempts.

### Teaching plans are persisted and auditable

Each session/practice pair can receive one `TutorPracticeTeachingArtifact`. It stores:

```text
strategy
focus topic
dominant mistake + count
recent attempt count
recent average score
recent average hint use
teaching intro
three coaching steps
teaching model name
```

Once materialized, repeated reads return the same teaching snapshot even if later session evidence changes. The table is new rather than an added column on existing practice rows, preserving the current create-only SQLAlchemy schema strategy.

### Session-aware hints

A new session-specific hint endpoint first resolves the persisted teaching plan, then reveals the existing hidden course hint and prepends the appropriate coaching step.

For example:

```text
Teaching plan:
Recurring sign-convention issue

Hint 1:
Choose and write the positive axis before doing any algebra.

[original grounded Hint 1 follows]
```

The underlying hint counter is shared with the existing standalone hint endpoint, so there is still only one sequence of three hints and no duplicate reveal path.

### Baseline, scaffolding, and challenge modes

When no recurring mistake dominates, StudyOS can use:

```text
baseline
reduce_scaffolding
reinforce
challenge
maintain
```

The first session question establishes a clean baseline. High recent hint dependence tells the student to complete the setup independently before opening support. Weak recent accuracy emphasizes slower explicit setup. Two strong unassisted answers switch the next item to `challenge`, asking for a fully independent attempt before any help is opened.

Cross-session practice IDs are validated before a teaching artifact or hint can be created.

## Practice-session memory and personalized remediation

StudyOS runs persisted multi-question practice sessions. The next-question policy uses the recent sequence rather than only the immediately previous answer:

```text
recent scores
+ hint usage
+ repeated mistake categories
+ topic-level performance
        ↓
session remediation policy
        ↓
next topic + difficulty
```

The active adaptation window is the latest five completed attempts, while the full session history remains available for reporting.

Repeated mistake evidence takes priority over a one-off score. High recent hint usage can trigger `reduce_scaffolding`; weak accuracy can reinforce the lowest-scoring recent topic; two strong unassisted answers can return control to the course-wide weakness optimizer. Sessions also enforce a hard `max_items` limit.

Practice-to-session membership is validated **before grading**, so another session's item cannot accidentally create score, mastery, or mistake evidence.

## Rubric-aware free-response grading

Practice evaluation supports:

```text
grading_provider: auto | local | openai
```

`auto` prefers the rubric-aware OpenAI grader when `OPENAI_API_KEY` is configured and otherwise uses the deterministic local grader. Explicit `openai` requests fail with `503` when the provider is not configured.

The OpenAI grader can accept mathematically or scientifically equivalent methods and award method credit rather than requiring lexical overlap with the reference solution.

StudyOS locally verifies the returned rubric before it can affect mastery:

- criterion maximums must sum to the item's mark total,
- awarded marks must stay inside each criterion range,
- confidence must be in `[0, 1]`,
- mistake categories must use the StudyOS taxonomy,
- duplicate mistake categories are collapsed to the strongest evidence,
- the final normalized score is recomputed locally.

Every evaluated practice attempt stores an auditable grading artifact with the grading mode, provider, criteria, awarded marks, and total marks.

Offline/CI evaluation remains available as `deterministic-reference-v1`.

## Adaptive practice loop

Practice now forms one continuous learning loop:

```text
weakness / requested topic
        ↓
grounded practice question
        ↓
session teaching plan
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
session-aware or one-shot adaptation
```

Correctness and mastery evidence remain separate. Hints do not turn a correct answer into a wrong one; instead they reduce how strongly that attempt updates mastery. Once the full solution is revealed, that item is no longer accepted as mastery evidence.

Standalone practice still uses the original one-attempt policy. Session memory and remediation activate only when a practice session is used.

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
- multi-question practice-session memory derived from immutable attempts
- persisted remediation teaching snapshots derived from recent attempt evidence

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
| `POST` | `/api/v1/courses/{course_id}/tutor/practice` | Create standalone grounded practice |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice-sessions` | Start adaptive multi-question session |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}` | Read session history/remediation state |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}/complete` | Complete session manually |
| `GET` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}/teaching` | Read/materialize current teaching plan |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice-sessions/{session_id}/practice/{practice_id}/hint` | Reveal remediation-aware hint |
| `POST` | `/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint` | Reveal standard next hint |
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
- [x] multi-question practice-session memory
- [x] recurring mistake and hint-dependence remediation
- [x] session-aware remediation explanations and hints
- [ ] persistent embedding index / vector database
- [ ] stronger entailment verifier

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

The next Phase 4 milestone is **persistent embedding storage and incremental vector indexing**: stop recomputing semantic embeddings on every retrieval request, store course chunk vectors with deterministic invalidation, and compare persistent semantic retrieval against the current reranking baseline.
