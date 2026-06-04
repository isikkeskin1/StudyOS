# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery over time, learns recurring mistake patterns, models forgetting, calibrates learning behavior from longitudinal evidence, estimates how study time changes the probability of reaching a target grade, and now measures those forecasts against real exam outcomes.

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
- Are StudyOS's historical forecasts actually accurate and well-calibrated?
- What should I deprioritize when time is running out?

## Current milestone — forecast outcome tracking and empirical calibration

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
- produce provisional expected-score distributions and target probabilities
- persist immutable pre-exam forecast snapshots
- attach the eventual real exam score to a saved snapshot
- calculate forecast MAE, RMSE, and signed bias
- measure likely-interval coverage against the nominal interval probability
- score target probabilities with Brier score and log loss
- compare mean predicted target probability with observed target-hit frequency
- classify the available outcome evidence as insufficient, preliminary, developing, or measured
- emit a cautious widen/stable/narrow uncertainty diagnostic only after at least three outcomes

Forecast snapshots are immutable by design. Once saved, the expected score, interval, target probability, evidence quality, thresholds, and assumptions remain exactly as they were before the outcome was known. This prevents later diagnostics or study activity from rewriting the historical prediction.

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
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots` | Generate and persist an immutable pre-exam forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-snapshots` | Read saved forecasts and attached outcomes |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots/{snapshot_id}/outcome` | Attach the actual exam grade to a saved forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-calibration` | Read empirical forecast accuracy/calibration metrics |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Forecast snapshots and outcomes

A forecast can be saved before the exam:

```json
{
  "label": "Physics I September written exam",
  "exam_date": "2026-09-15",
  "forecast": {
    "study_hours": 18,
    "target_grade": 25,
    "desired_probability": 0.8,
    "interval_probability": 0.8,
    "thresholds": [18, 21, 24, 25, 27]
  }
}
```

The saved record preserves the original model/version, expected grade, uncertainty, interval, target probability, evidence quality/confidence, threshold probabilities, request payload, and model assumptions.

After the exam, attach the observed grade:

```json
{
  "actual_grade": 26,
  "occurred_at": "2026-09-15"
}
```

A snapshot accepts only one outcome. The actual grade cannot exceed the score maximum that was stored with that historical forecast.

## Empirical forecast calibration

`GET /api/v1/courses/{course_id}/forecast-calibration` evaluates completed forecast/outcome pairs.

### Score accuracy

StudyOS reports:

```text
mean_absolute_error
root_mean_squared_error
mean_signed_error
```

Signed error is `forecast - actual`, so a positive mean indicates systematic overprediction and a negative mean indicates underprediction.

### Interval calibration

StudyOS reports the fraction of real grades that landed inside the saved likely-score interval and compares it with the average nominal interval probability:

```text
interval_coverage
average_nominal_interval_probability
coverage_gap
average_interval_width
```

If nominal 80% intervals only contain 55% of outcomes, the uncertainty model is likely too narrow. If they contain nearly every outcome, the interval may be too wide. The current `widen / stable / narrow` diagnostic is only emitted once at least three outcomes exist.

### Probability calibration

For the saved target threshold, StudyOS records whether the student actually met the target and evaluates the stored probability with:

```text
mean_target_probability
observed_target_rate
target_calibration_gap
brier_score
log_loss
```

Lower Brier score and log loss are better. The calibration gap is descriptive: with enough independent outcomes, predicted target probabilities should broadly agree with observed target-hit frequencies.

### Evidence maturity

Calibration status is intentionally conservative:

```text
< 3 outcomes   insufficient_data
3–9 outcomes   preliminary
10–29 outcomes developing
30+ outcomes   measured
```

These labels describe sample maturity, not proof that the model is statistically valid. Repeated forecasts for highly similar exams are also not guaranteed to be independent observations.

## Probabilistic grade model

`probabilistic-v1` uses the inspectable `heuristic-v5` planner as its expected-score model and places a provisional uncertainty distribution around that mean.

A forecast can expose:

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

Forecast uncertainty contracts with stronger measured topic coverage, effective mastery confidence, past-paper evidence, and longitudinal learning/retention evidence. Longer future study horizons add a small uncertainty penalty.

Probability outputs remain **provisional**. Persisting outcomes now gives StudyOS the data needed to test and eventually recalibrate those assumptions rather than simply declaring them calibrated.

## Learning, retention, and planning calibration

The learning/retention calibration endpoint exposes each topic's history count, evidence span, learning-rate multiplier, learning scale, learning confidence, observed gain per evidence, heuristic/calibrated retention half-life, retention confidence, observation count, and calibration source.

Diagnostic response duration is **not** treated as study time. Learning-rate adjustments are confidence-shrunk toward the generic curve, while retention estimates only use meaningful time-separated performance drops.

The current `heuristic-v5` planner combines course importance, past-paper exam weight, forgetting-adjusted mastery, mistake focus, personalized learning scale, and calibrated retention half-life. The probability layer remains separate so its uncertainty assumptions can be backtested without hiding the underlying study-allocation logic.

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
- [x] immutable pre-exam forecast snapshots
- [x] real exam outcome attachment
- [x] MAE/RMSE/bias backtesting
- [x] interval coverage diagnostics
- [x] Brier/log scoring and target calibration gap
- [ ] guarded empirical recalibration of uncertainty/probabilities
- [ ] calibration buckets/reliability curves across larger samples

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
7. Call `/grade-forecast` while exploring possible study-hour budgets.
8. Before the real exam, persist the chosen state with `/forecast-snapshots`.
9. After the exam, attach the real grade to that snapshot.
10. Use `/forecast-calibration` to inspect accuracy, interval coverage, and probability calibration over time.

The next Phase 3 milestone is **guarded empirical recalibration**: use accumulated real outcomes to adjust future uncertainty width only when sample maturity is high enough, while preserving the raw uncalibrated forecast for auditability.