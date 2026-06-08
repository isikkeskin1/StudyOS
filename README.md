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
- What should I deprioritize when time is running out?

## Current milestone — practice-session memory and personalized remediation

The backend is now at **v0.22.0**.

StudyOS can now run persisted multi-question practice sessions. The next-question policy uses the recent sequence rather than only the immediately previous answer:

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

A session keeps the last five completed attempts as its active adaptation window while retaining the full session history for reporting.

### Recurring mistake remediation

Repeated mistake evidence takes priority over a one-off score. If the same mistake category occurs at least twice in the recent window, StudyOS identifies which topic contributed the greatest severity and can return:

```text
remediate_pattern
```

For example:

```text
Recent mechanics attempts
1. sign error
2. sign error
3. correct answer

→ dominant mistake: sign
→ focus topic: topic carrying the largest sign-error burden
→ keep or lower difficulty before moving on
```

This state is derived from stored practice attempts and mistake rows; StudyOS does not maintain a second hidden mastery score for the session.

### Hint dependence and strong streaks

Session adaptation can return:

```text
remediate_pattern
reduce_scaffolding
reinforce
maintain
increase_difficulty
session_reoptimize
session_complete
```

High recent hint usage can trigger `reduce_scaffolding`, keeping the student on the same topic with less difficulty pressure. Two strong unassisted answers in a row can trigger `session_reoptimize`, returning control to the course-wide weakness selector.

Sessions also have a hard `max_items` limit. Reaching it marks the session completed and prevents another automatic item from being created.

### Session integrity

Practice-to-session membership is validated **before grading**. A practice item from another session is rejected before score, mastery, or mistake evidence can be persisted.

Session state uses two new tables rather than altering existing practice rows:

```text
TutorPracticeSession
TutorPracticeSessionItem
```

That keeps this milestone compatible with the current create-only SQLAlchemy schema strategy.

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

Standalone practice still uses the original one-attempt policy. Session-aware behavior activates only when `session_id` is supplied to the evaluation request.

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
- [x] multi-question practice-session memory
- [x] recurring mistake and hint-dependence remediation
- [ ] persistent embedding index / vector database
- [ ] stronger entailment verifier
- [ ] session-aware remediation explanations and hints

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

The next Phase 4 milestone is **session-aware remediation explanations and hints**: use the session's dominant mistake pattern and unresolved topic context to tailor explanations and hint wording without revealing the answer or creating a second hidden mastery state.
