# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery over time, learns recurring mistake patterns, models forgetting, calibrates learning behavior from longitudinal evidence, and estimates how study time changes the probability of reaching a target grade.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS aims to answer

- What should I study next?
- How many focused hours should I invest?
- Which topics matter most for the exam?
- What grade is realistic with the time I have?
- What score range is plausible rather than just one point estimate?
- What is the current probability of reaching my target grade?
- How many hours are needed for a chosen probability of reaching that target?
- Which weak topics offer the highest expected improvement per hour?
- Why am I repeatedly losing marks?
- Which topics are becoming stale and need review?
- Does this student appear to learn or forget this topic faster than the generic model assumes?
- What should I deprioritize when time is running out?

## Current milestone — probabilistic grade forecasting

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
- preserve response-level mastery history and trend analytics
- calibrate per-topic learning responsiveness and retention conservatively
- feed calibrated learning/retention signals into planning and review scheduling
- convert the planner point estimate into a provisional score distribution
- expose expected score, standard deviation, and a configurable likely-score interval
- estimate `P(score >= threshold)` for the target and arbitrary requested thresholds
- generate probability-aware study-hour scenarios
- estimate hours required for a requested probability of reaching a target
- expose evidence quality so clients can distinguish weak from stronger forecasts
- widen uncertainty slightly for longer future study horizons

The probability layer is intentionally labelled **provisional**. It is useful for planning and comparing scenarios, but it is not yet statistically calibrated against held-out real exam outcomes. StudyOS therefore never presents the probability as a guarantee.

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
| `POST` | `/api/v1/courses/{course_id}/grade-forecast` | Generate a provisional probability-aware grade forecast |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Probabilistic grade model

A forecast request can specify study hours, a target grade, arbitrary score thresholds, the desired probability for target planning, and an interval probability:

```json
{
  "study_hours": 18,
  "target_grade": 25,
  "desired_probability": 0.8,
  "interval_probability": 0.8,
  "thresholds": [18, 21, 24, 25, 27]
}
```

The response exposes:

```text
forecast_model: probabilistic-v1
probability_status: provisional
evidence_quality
evidence_confidence
expected_grade
standard_deviation
likely_range_low
likely_range_high
target_probability
threshold probabilities
required-hours sensitivity band
study-hour scenarios
```

The expected score still comes from the inspectable `heuristic-v5` planner. The probability layer adds uncertainty around that estimate rather than pretending the planner itself has become ground truth.

### Evidence quality

Forecast uncertainty contracts as StudyOS gains stronger evidence from:

1. measured topic coverage
2. effective mastery confidence
3. past-paper question/mark evidence
4. longitudinal learning and retention history

Longer future study horizons add a small uncertainty penalty because projected learning becomes less certain farther from observed evidence.

### Required hours for a target probability

StudyOS can answer a planning question such as:

```text
Target: 25 / 30
Desired probability: 80%
Estimated required study: 24.5h
Optimistic sensitivity: 21.0h
Conservative sensitivity: 29.0h
```

The optimistic/conservative values are **sensitivity bounds produced by changing the uncertainty width by ±15%**. They are not a formal statistical confidence interval for study time.

### Probability limitations

`probabilistic-v1` currently uses a normal approximation around the planner mean and a transparent evidence-quality uncertainty heuristic. The score interval is bounded to the valid course grade range, while threshold probabilities remain provisional approximations.

The next calibration step is to record real exam outcomes, preserve the forecast that existed before each exam, and measure whether statements such as “80% chance” actually occur roughly 80% of the time.

## Calibration model

The learning/retention calibration endpoint exposes each topic's history count, evidence span, learning-rate multiplier, learning scale, learning confidence, observed gain per evidence, heuristic/calibrated retention half-life, retention confidence, observation count, and calibration source.

Diagnostic response duration is **not** treated as study time. Learning-rate adjustments are confidence-shrunk toward the generic curve, while retention estimates only use meaningful time-separated performance drops.

## Mastery, retention, and mistakes

Each scored diagnostic response records one mastery-history point for every affected topic. StudyOS derives recent accuracy, trend direction/confidence, evidence span, and observed mastery gain while preserving raw mastery separately from forgetting-adjusted effective mastery.

The review queue combines evidence age, effective mastery, exam weight, exam proximity, and the active retention half-life. Mistake intelligence separately tracks recurring concept, formula-selection, algebra, arithmetic, sign, unit, interpretation, incomplete-reasoning, careless, and other errors.

## Study-plan model

The current `heuristic-v5` planner combines:

1. **Course importance** from the topic graph.
2. **Exam weight** from past-paper frequency and known marks.
3. **Forgetting-adjusted mastery gap** from measured diagnostic evidence, explicit overrides, or the fallback baseline.
4. **Mistake focus** from classified error patterns.
5. **Personalized learning scale** from longitudinal mastery movement when available.
6. **Calibrated retention half-life** from time-separated performance evidence when available.

The planner remains inspectable, and the probability layer is kept separate so confidence/uncertainty assumptions can evolve without hiding the underlying study-allocation logic.

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
- [x] expected-score distributions around planner projections
- [x] configurable likely-score intervals
- [x] target and arbitrary threshold probabilities
- [x] probability-aware study-time scenarios
- [x] required-hours estimates for a chosen target probability
- [x] evidence-quality-driven uncertainty width
- [ ] persist pre-exam forecasts and real exam outcomes
- [ ] backtesting, calibration curves, Brier/log scoring, and interval coverage
- [ ] empirically recalibrate probability/uncertainty parameters

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
3. Build the course topic graph and exam intelligence.
4. Accumulate diagnostic evidence and inspect mastery/mistake trends.
5. Use `/calibration` and `/reviews` to understand learning speed and staleness.
6. Generate `/study-plan` for topic-level allocation.
7. Call `/grade-forecast` with candidate study-hour budgets and target thresholds.
8. Compare the expected score, likely range, target probability, and required-hours band.

The next Phase 3 milestone is **forecast/outcome tracking and empirical calibration** so StudyOS can learn whether its probability statements are actually reliable over real exams.