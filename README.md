# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery over time, learns recurring mistake patterns, models forgetting, calibrates learning behavior from longitudinal evidence, estimates how study time changes the probability of reaching a target grade, and measures those forecasts against real exam outcomes.

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
- How should future forecasts change when real outcomes show systematic bias or bad uncertainty width?
- What should I deprioritize when time is running out?

## Current milestone — guarded empirical forecast recalibration

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
- persist immutable pre-exam forecast snapshots and attach real exam outcomes
- calculate MAE, RMSE, signed bias, interval coverage, Brier score, and log loss
- derive a guarded empirical score-bias correction from historical raw forecasts
- derive a guarded uncertainty-width multiplier from normalized historical residuals
- activate empirical corrections only after at least five completed forecast/outcome pairs
- shrink corrections toward no adjustment until more evidence accumulates
- cap score-bias corrections to ±5% of the course grade scale
- cap raw uncertainty-width estimates to `0.75x–1.35x` before shrinkage
- expose raw and empirically adjusted forecasts side-by-side
- persist adjusted forecast snapshots with a one-to-one raw forecast artifact for auditability
- train empirical corrections from raw predictions even when historical snapshots were adjusted, preventing feedback loops

The raw `probabilistic-v1` forecast is never silently overwritten. Empirical recalibration is an explicit wrapper (`probabilistic-v1+empirical-v1`) and remains labelled provisional. With fewer than five completed outcomes, the calibrated endpoint returns the raw forecast values exactly unchanged.

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
| `POST` | `/api/v1/courses/{course_id}/grade-forecast` | Generate the raw provisional probability-aware grade forecast |
| `POST` | `/api/v1/courses/{course_id}/grade-forecast/calibrated` | Generate raw + guarded empirically adjusted forecast output |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots` | Persist a raw or adjusted immutable pre-exam forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-snapshots` | Read saved forecasts, raw artifacts, and attached outcomes |
| `POST` | `/api/v1/courses/{course_id}/forecast-snapshots/{snapshot_id}/outcome` | Attach the actual exam grade to a saved forecast |
| `GET` | `/api/v1/courses/{course_id}/forecast-calibration` | Read empirical accuracy metrics and active recalibration state |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Guarded empirical recalibration

`POST /api/v1/courses/{course_id}/grade-forecast/calibrated` first computes the unchanged raw `probabilistic-v1` forecast, then derives an empirical adjustment from completed saved forecast/outcome pairs.

The response keeps both layers:

```text
raw_forecast
recalibration
expected_grade
standard_deviation
likely_range_low
likely_range_high
target_probability
threshold probabilities
adjusted study-hour scenarios
```

The recalibration object exposes:

```text
active
calibration_model
calibration_status
paired_outcome_count
shrinkage_weight
raw_bias_marks
applied_bias_marks
raw_width_multiplier
applied_width_multiplier
```

### Activation and shrinkage

Empirical corrections stay inactive until five completed outcomes exist:

```text
0–4 outcomes    inactive
5–9 outcomes    guarded
10–29 outcomes  developing
30+ outcomes    measured
```

Once active, the correction weight grows toward full influence by 20 completed outcomes. A five-outcome sample therefore cannot apply the raw empirical correction at full strength.

### Mean correction

For each historical forecast, StudyOS measures:

```text
residual = actual_grade - raw_expected_grade
```

The mean residual estimates score bias. Before shrinkage, it is capped to ±5% of the course grade scale. A systematic overprediction on a 30-point exam can therefore never immediately shift the model by more than ±1.5 marks even with extreme historical data.

### Uncertainty-width correction

StudyOS centers residuals around the empirical bias and compares the remaining error spread with each forecast's raw standard deviation. The resulting width multiplier is capped to:

```text
0.75x <= raw_width_multiplier <= 1.35x
```

The capped multiplier is then shrunk toward `1.0x` according to evidence maturity.

### Feedback-loop protection

Adjusted forecast snapshots can be persisted with:

```json
{
  "label": "Physics I final",
  "apply_recalibration": true,
  "forecast": {
    "study_hours": 18,
    "target_grade": 25
  }
}
```

The visible snapshot stores the adjusted prediction. A one-to-one recalibration artifact separately stores the raw expected score, raw uncertainty, raw interval, raw target probability, raw threshold probabilities, and the exact correction used.

When StudyOS later estimates a new empirical correction, it trains from those preserved **raw** values rather than from its own previously adjusted output. This avoids a recursive self-calibration loop.

## Forecast snapshots and outcomes

A raw forecast snapshot can still be saved with the existing request format; `apply_recalibration` defaults to `false` for backwards-compatible baseline tracking.

After the exam, attach the observed grade:

```json
{
  "actual_grade": 26,
  "occurred_at": "2026-09-15"
}
```

A snapshot accepts only one outcome. The actual grade cannot exceed the score maximum stored with that historical forecast.

## Empirical forecast diagnostics

`GET /api/v1/courses/{course_id}/forecast-calibration` evaluates completed forecast/outcome pairs and now also exposes the currently active empirical recalibration state.

StudyOS reports:

```text
mean_absolute_error
root_mean_squared_error
mean_signed_error
interval_coverage
average_nominal_interval_probability
coverage_gap
average_interval_width
mean_target_probability
observed_target_rate
target_calibration_gap
brier_score
log_loss
uncertainty_direction
empirical_recalibration
```

Signed error is `forecast - actual`, so positive values indicate overprediction. Brier score and log loss evaluate target-threshold probabilities; lower values are better. Interval coverage should be compared with the nominal interval probability.

These diagnostics evaluate the forecast that was actually shown and saved. The recalibration estimator separately uses preserved raw predictions where adjusted artifacts exist.

## Probabilistic grade model

The raw `probabilistic-v1` layer uses the inspectable `heuristic-v5` planner as its expected-score model and places a provisional uncertainty distribution around that mean.

Forecast uncertainty contracts with stronger measured topic coverage, effective mastery confidence, past-paper evidence, and longitudinal learning/retention evidence. Longer future study horizons add a small uncertainty penalty.

Empirical recalibration does not turn these values into guaranteed probabilities. The model still needs substantially more independent real exam outcomes, reliability-curve analysis, and held-out evaluation before its probabilities should be described as statistically calibrated.

## Learning, retention, and planning calibration

The learning/retention calibration endpoint exposes each topic's history count, evidence span, learning-rate multiplier, learning scale, learning confidence, observed gain per evidence, heuristic/calibrated retention half-life, retention confidence, observation count, and calibration source.

Diagnostic response duration is **not** treated as study time. Learning-rate adjustments are confidence-shrunk toward the generic curve, while retention estimates only use meaningful time-separated performance drops.

The current `heuristic-v5` planner combines course importance, past-paper exam weight, forgetting-adjusted mastery, mistake focus, personalized learning scale, and calibrated retention half-life.

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
- [x] guarded empirical score-bias recalibration
- [x] guarded empirical uncertainty-width recalibration
- [x] raw-vs-adjusted forecast audit trail
- [ ] calibration buckets and reliability curves across larger samples
- [ ] held-out evaluation and model-version comparison

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
7. Call `/grade-forecast` to inspect the unchanged raw probability model.
8. Record raw pre-exam snapshots and real outcomes as evidence accumulates.
9. Use `/forecast-calibration` to inspect historical error and calibration maturity.
10. Call `/grade-forecast/calibrated` to compare the raw prediction with the guarded empirical adjustment.
11. If desired, persist an adjusted forecast with `apply_recalibration=true`; StudyOS stores the raw prediction alongside it for auditability.

The next Phase 3 milestone is **reliability curves and model-version evaluation**: bucket historical probability forecasts, compare predicted vs observed frequencies, and evaluate raw versus empirically adjusted model versions on held-out outcomes instead of relying only on aggregate metrics.
