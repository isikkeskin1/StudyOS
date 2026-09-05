# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery over time, learns recurring mistake patterns, grades supported diagnostic answers against extracted solutions, models forgetting, calibrates learning behavior from longitudinal evidence, and recommends how to spend limited study time around a target grade.

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
- Does this student appear to learn or forget this topic faster than the generic model assumes?
- What should I deprioritize when time is running out?

## Current milestone — personalized learning and retention calibration

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
- preserve response-level mastery history for every affected topic
- calculate trend direction, recent accuracy, and evidence span
- estimate observed mastery gain per unit of diagnostic evidence
- derive confidence-shrunk per-topic learning-rate multipliers
- convert those multipliers into personalized diminishing-return study curves
- estimate retention half-life from time-separated performance drops when evidence exists
- blend sparse retention observations back toward the generic retention heuristic
- expose calibration confidence and whether a topic is heuristic, blended, or personalized
- feed personalized learning scales into the study-time optimizer
- feed calibrated retention half-lives into effective mastery and review scheduling

The calibration layer is deliberately conservative. Diagnostic response duration is **not** treated as study time. Learning-rate multipliers only adjust the generic study-gain curve relative to observed mastery movement, and low-confidence estimates are strongly shrunk toward the default model. Retention calibration only uses time-separated performance drops and remains heuristic until enough repeated evidence exists.

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
| `GET` | `/api/v1/courses/{course_id}/mastery/history` | Read response-level mastery timelines and trend analytics |
| `GET` | `/api/v1/courses/{course_id}/calibration` | Read personalized learning and retention calibration |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read course-level mistake intelligence |
| `GET` | `/api/v1/courses/{course_id}/reviews` | Read forgetting-aware review recommendations |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Generate a target-grade study plan |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Calibration model

Each topic exposes:

```text
history_point_count
evidence_span_days
learning_rate_multiplier
learning_scale_hours
learning_confidence
observed_gain_per_evidence
heuristic_half_life_days
retention_half_life_days
retention_confidence
retention_observation_count
calibration_source
```

### Learning calibration

The generic planner starts with a `2.8h` diminishing-return learning scale. StudyOS measures how mastery moved per unit of diagnostic evidence, converts the signed trend into a bounded learning-rate adjustment, and shrinks that adjustment according to the amount of evidence available.

A positive longitudinal signal can therefore produce a slightly smaller learning scale, while repeated negative movement can produce a larger one. The model does **not** claim that diagnostic answering time is equivalent to focused study time.

### Retention calibration

The generic retention half-life is still derived from raw mastery, confidence, and accumulated evidence. When StudyOS observes repeated performance drops separated by meaningful time gaps, it estimates an empirical half-life from those drops and blends that estimate with the generic half-life.

Sparse observations remain low confidence and stay close to the generic model. Medium/high-confidence calibrated half-lives are used by the review queue and by forgetting-adjusted mastery in the planner.

## Mastery history model

Each scored diagnostic response records one history point for every mapped topic affected by the response:

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

The history endpoint derives raw/effective mastery, mastery change, weekly change when enough time has elapsed, recent accuracy, trend direction, trend confidence, and observed gain per unit of evidence.

## Retention and review model

StudyOS preserves raw measured mastery and derives effective mastery at read/planning time. The review queue combines evidence age, effective mastery, exam weight, exam proximity, and the active retention half-life to decide what is due and how many review minutes to recommend.

Review items report whether retention is still using the generic heuristic or a calibrated longitudinal estimate.

## Automatic grading model

For a processed document classified as `past_exam_solution`, StudyOS separates inline `Solution:` / `Answer:` content from the visible question prompt. Diagnostic clients never receive the extracted solution before submission.

The current deterministic grader checks answer-specific concept/token coverage, numerical-result agreement, sign mismatches, and common unit agreement. Grader confidence and evidence coverage are reported separately from student confidence. If no reference solution was safely extracted, automatic grading returns `409` instead of inventing a mark.

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

## Study-plan model

The current `heuristic-v5` planner combines:

1. **Course importance** from the topic graph.
2. **Exam weight** from past-paper frequency and known marks.
3. **Forgetting-adjusted mastery gap** from measured diagnostic evidence, explicit overrides, or the fallback baseline.
4. **Mistake focus** from classified error patterns.
5. **Personalized learning scale** from longitudinal mastery movement when available.
6. **Calibrated retention half-life** from time-separated performance evidence when available.

The output exposes per-topic calibration source/confidence so downstream clients can distinguish generic estimates from evidence-backed adjustments. Grade projections remain planning heuristics rather than calibrated probabilities or guarantees.

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
- [x] confidence-shrunk personalized learning calibration
- [x] longitudinal retention-half-life calibration
- [ ] richer grading adapters / rubric-aware grading

### Phase 3 — Grade modelling
Expected-score distributions, target-grade probabilities, study-time simulations, calibration against observed exam outcomes, and uncertainty tracking.

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
4. Build question-level exam intelligence.
5. Start diagnostics and accumulate scored topic evidence.
6. Read `/mastery/history` for longitudinal learning curves.
7. Read `/calibration` to see which learning/retention parameters are still generic and which have evidence behind them.
8. Read `/mistakes` for recurring errors and `/reviews` for stale topics.
9. Generate a study plan; StudyOS now uses personalized learning scales and calibrated retention where evidence is sufficient.

The next milestone is **Phase 3 probabilistic grade modelling**: turn mastery, exam weights, calibration confidence, and study-time scenarios into score ranges and target-grade probabilities rather than single heuristic point estimates.