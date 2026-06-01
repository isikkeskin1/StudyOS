# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery over time, learns recurring mistake patterns, grades supported diagnostic answers against extracted solutions, models forgetting, and recommends how to spend limited study time around a target grade.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS aims to answer

- What should I study next?
- How many focused hours should I invest?
- Which topics matter most for the exam?
- What grade is realistic with the time I have?
- How much time is likely required to reach my target?
- Which weak topics offer the highest expected improvement per hour?
- Why am I repeatedly losing marks?
- Am I actually improving on a topic, or just seeing noisy results?
- Which topics are becoming stale and need review?
- What should I deprioritize when time is running out?

## Current milestone — mastery history and trend analytics

The backend can now:

- create courses with exam dates and target grades
- upload and deduplicate `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md` material
- extract source-aware text from supported document formats
- preserve PDF page and PowerPoint slide references
- build a course-level topic graph with source evidence
- extract numbered past-paper questions and explicit mark values
- calculate normalized exam weights from marks and question frequency
- create adaptive diagnostic sessions from real past-paper questions
- maintain Bayesian topic-mastery estimates and confidence
- store submitted answers, reference answers, feedback, and recurring mistake evidence
- automatically grade supported answers against extracted reference solutions
- keep extracted solutions hidden until an answer is submitted
- discount stale diagnostic mastery with a transparent forgetting curve
- generate an exam-aware review queue with recommended review minutes
- feed forgetting-adjusted mastery into adaptive diagnostics and study planning
- persist one mastery-history snapshot for every topic affected by every scored response
- expose the exact source score, topic relevance, and evidence increment behind each history point
- calculate per-topic raw mastery change, effective mastery, recent accuracy, and evidence span
- classify learning trends as improving, stable, declining, or insufficient-data
- report trend confidence separately from trend direction
- estimate observed mastery gain per unit of diagnostic evidence without treating it as a calibrated learning rate
- rebuild legacy history deterministically from existing diagnostic responses when needed

Trend analytics are deliberately evidence-aware. A same-day burst of two responses may show a direction, but it remains low confidence and does not pretend to be a reliable weekly learning rate. Longitudinal estimates only become stronger as evidence accumulates across time.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create a course |
| `GET` | `/api/v1/courses` | List courses |
| `GET` | `/api/v1/courses/{course_id}` | Get one course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload course material |
| `GET` | `/api/v1/courses/{course_id}/documents` | List uploaded material |
| `POST` | `/api/v1/courses/{course_id}/documents/{document_id}/process` | Extract and classify a document |
| `GET` | `/api/v1/courses/{course_id}/documents/{document_id}/content` | Read source units and chunks |
| `POST` | `/api/v1/courses/{course_id}/analyze` | Build or rebuild course intelligence |
| `GET` | `/api/v1/courses/{course_id}/intelligence` | Read topics, evidence, and relationships |
| `POST` | `/api/v1/courses/{course_id}/exam-intelligence/analyze` | Analyze questions, marks, topic weights, and solution references |
| `GET` | `/api/v1/courses/{course_id}/exam-intelligence` | Read past-paper intelligence and grading availability |
| `POST` | `/api/v1/courses/{course_id}/diagnostics` | Start an adaptive diagnostic |
| `GET` | `/api/v1/courses/{course_id}/diagnostics/{session_id}` | Read diagnostic progress |
| `GET` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/next` | Get the next adaptive question |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/responses` | Manually/self score a response and optionally store answer/mistake evidence |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/grade` | Automatically grade an answer against an extracted reference solution |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/complete` | End a diagnostic early |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read measured raw topic mastery |
| `GET` | `/api/v1/courses/{course_id}/mastery/history` | Read topic mastery timelines and learning-trend analytics |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read course-level mistake intelligence |
| `GET` | `/api/v1/courses/{course_id}/reviews` | Read forgetting-aware review recommendations |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Generate a target-grade study plan |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Mastery history model

Each scored diagnostic response contributes evidence to every mapped topic. After the response, StudyOS records a snapshot for each affected topic containing:

```text
response_id
recorded_at
mastery
confidence
evidence_weight
response_count
source_score
topic_relevance
evidence_increment
```

The history endpoint then derives per-topic analytics:

```text
raw_mastery
effective_mastery
confidence
effective_confidence
forgetting_risk
change_from_first
weekly_change
trend_direction
trend_confidence
recent_accuracy
recent_response_count
observed_gain_per_evidence
first_evidence_at
latest_evidence_at
evidence_span_days
```

`weekly_change` is only emitted once the evidence spans at least a day. `observed_gain_per_evidence` is an empirical signal, not yet a personalized learning-rate parameter.

## Retention and review model

StudyOS preserves the raw mastery inferred from diagnostic evidence, then computes an effective mastery at read/planning time.

The current retention baseline uses an exponential half-life with a memory floor. The half-life grows with measured mastery, confidence, and accumulated evidence weight. Strong, repeated evidence therefore decays more slowly than one weak diagnostic answer. Confidence also decays separately so old evidence becomes less trustworthy even before estimated mastery falls sharply.

Each review recommendation exposes raw/effective mastery, raw/effective confidence, evidence age, half-life, forgetting loss/risk, exam weight, review priority, due state, recommended minutes, and an inspectable reason.

Exam proximity shortens review intervals, while high exam-weight topics receive higher review priority. Unmeasured topics are treated as study targets rather than review targets.

## Automatic grading model

For a processed document classified as `past_exam_solution`, StudyOS looks for inline solution markers such as:

```text
Question 1 (8 marks)
Calculate the force.
Solution: F = ma, so the force is 10 N.
```

Exam analysis stores the prompt and reference solution separately. Diagnostic clients receive only the prompt before submission.

The deterministic grader currently checks answer-specific concept/token coverage, numerical-result agreement, sign mismatches, and common unit agreement. The response records grader confidence and evidence coverage separately from student confidence. If no reference solution was safely extracted, automatic grading returns `409` rather than inventing a mark.

## Mistake model

Supported mistake categories:

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

Each label has a severity and source (`self`, `manual`, or `automatic`). StudyOS aggregates category occurrence counts, weighted lost-score contribution, classification coverage, per-topic mistake burden, and dominant mistake categories.

## Mastery model

Each diagnostic response contributes weighted evidence to every topic mapped to the source exam question. Evidence strength considers topic relevance, estimated question difficulty, response confidence, and the normalized score.

Topic mastery uses a Bayesian prior and reports confidence separately, so one lucky or unlucky answer cannot create fake certainty. The raw mastery remains stored; forgetting is applied as a derived layer rather than destructively rewriting measured evidence.

## Study-plan model

The current `heuristic-v4` planner combines:

1. **Course importance** from the topic graph.
2. **Exam weight** from past-paper frequency and known marks.
3. **Forgetting-adjusted mastery gap** from measured diagnostic evidence, explicit overrides, or the fallback baseline.
4. **Mistake focus** from classified error patterns.

Explicit topic mastery overrides remain authoritative and are not decayed. Stored diagnostic mastery is converted to effective mastery at plan time. Mistake burden slightly increases study priority but does not directly lower projected grades; the underlying diagnostic score already affects mastery.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] course model and persistence
- [x] document upload and metadata
- [x] PDF/DOCX/PPTX/TXT/MD text extraction
- [x] document chunking and source references
- [x] baseline document classification
- [x] baseline concept and topic extraction
- [x] past-paper question structure extraction
- [x] topic weighting and exam-frequency signals
- [x] first study-plan engine

### Phase 2 — Diagnostics and mastery
- [x] adaptive diagnostic sessions
- [x] persistent topic mastery estimates
- [x] mastery confidence / evidence tracking
- [x] diagnostic-aware study replanning
- [x] answer capture and feedback evidence
- [x] mistake classification infrastructure
- [x] mistake-pattern analytics and planner feedback
- [x] deterministic automatic grading adapter
- [x] inline solution extraction with prompt/reference separation
- [x] forgetting-aware effective mastery
- [x] exam-aware review queue and review-minute recommendations
- [x] response-level mastery history
- [x] trend direction, recent accuracy, and evidence-span analytics
- [ ] richer grading adapters / rubric-aware grading
- [ ] personalized learning/forgetting parameter calibration

### Phase 3 — Grade modelling
Expected-score ranges, target-grade probabilities, study-time simulations, calibration, and uncertainty tracking.

### Phase 4 — Course-aware tutor
Retrieval over uploaded material, cited explanations, exam-style questions, and guided problem solving.

### Phase 5 — Optimization
Expected marks per study hour, emergency mode, automatic rescheduling, and multi-course optimization.

### Phase 6 — Study operating system
Semester dashboard, spaced repetition, personalized cheat sheets, analytics, calendar integration, and PWA support.

## Tech stack

**Current**

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2
- SQLite
- pypdf
- python-docx
- python-pptx
- Pytest
- Ruff
- GitHub Actions

**Planned**

- Next.js / TypeScript
- PostgreSQL
- Redis
- background workers
- vector retrieval
- Docker
- LLM-assisted grading and course analysis

## Local development

```bash
cd backend
python -m venv .venv
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to use the API interactively.

Run checks:

```bash
ruff check .
pytest
```

## Example flow

1. Create a course with a target grade and optional exam date.
2. Upload and process lectures and past papers/solutions.
3. Build the course topic graph with `/analyze`.
4. Build question-level exam intelligence; supported inline solutions are separated from prompts.
5. Start a diagnostic and work through adaptive questions without seeing reference solutions.
6. Automatically grade supported answers through `/grade`, or use the manual response endpoint when needed.
7. Read `/mastery/history` to see response-level learning curves, recent accuracy, trend direction, and trend confidence.
8. Read `/mistakes` for recurring error patterns and `/reviews` for stale topics that need reinforcement.
9. Generate a study plan; StudyOS uses forgetting-adjusted mastery plus mistake focus when allocating time.

The next milestone is **personalized learning/forgetting calibration**, then Phase 3 grade modelling can start using the student's observed longitudinal performance instead of generic learning constants.