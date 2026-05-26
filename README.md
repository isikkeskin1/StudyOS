# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery, learns recurring mistake patterns, and recommends how to spend limited study time around a target grade.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS aims to answer

- What should I study next?
- How many focused hours should I invest?
- Which topics matter most for the exam?
- What grade is realistic with the time I have?
- How much time is likely required to reach my target?
- Which weak topics offer the highest expected improvement per hour?
- Why am I repeatedly losing marks?
- What should I deprioritize when time is running out?

## Current milestone — mistake intelligence and answer evidence

The backend can now:

- create courses with exam dates and target grades
- upload and deduplicate `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md` material
- extract source-aware text from supported document formats
- preserve PDF page and PowerPoint slide references
- build a course-level topic graph with source evidence
- extract numbered past-paper questions and explicit mark values
- calculate normalized exam weights from marks and question frequency
- generate target-grade study-time plans with diminishing returns
- create adaptive diagnostic sessions from real past-paper questions
- maintain Bayesian topic-mastery estimates and confidence
- store the student's submitted answer, reference answer, and feedback
- classify mistakes as concept, formula selection, algebra, arithmetic, sign, units, interpretation, incomplete reasoning, careless, or other
- record mistake severity and classification source
- aggregate lost-score patterns across the course
- calculate per-topic mistake burden and dominant mistake categories
- report how much lost-score evidence has actually been classified
- feed classified mistake patterns back into study priority without double-counting them in the grade estimate

The planning engine remains a transparent heuristic rather than a calibrated grade predictor. Diagnostic scores affect mastery; mistake labels affect *what to focus on while studying*, not the grade estimate a second time.

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
| `POST` | `/api/v1/courses/{course_id}/exam-intelligence/analyze` | Analyze questions, marks, and topic weights |
| `GET` | `/api/v1/courses/{course_id}/exam-intelligence` | Read past-paper intelligence |
| `POST` | `/api/v1/courses/{course_id}/diagnostics` | Start an adaptive diagnostic |
| `GET` | `/api/v1/courses/{course_id}/diagnostics/{session_id}` | Read diagnostic progress |
| `GET` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/next` | Get the next adaptive question |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/responses` | Score a response and optionally store answer/mistake evidence |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/complete` | End a diagnostic early |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read measured topic mastery |
| `GET` | `/api/v1/courses/{course_id}/mistakes` | Read course-level mistake intelligence |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Generate a target-grade study plan |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Mistake model

A scored diagnostic response may include answer evidence and zero or more mistake labels.

Supported categories:

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

Each label has a severity and source (`self`, `manual`, or `automatic`). StudyOS aggregates the lost-score evidence behind those labels and reports:

- category occurrence counts
- weighted lost-score contribution
- share of classified loss
- classification coverage
- per-topic mistake burden
- dominant mistake categories per topic

This keeps mistake analysis inspectable and makes it possible to add automatic graders later without changing the public data model.

## Mastery model

Each diagnostic response contributes weighted evidence to every topic mapped to the source exam question. Evidence strength considers topic relevance, estimated question difficulty, response confidence, and the normalized score.

Topic mastery uses a Bayesian prior and reports confidence separately, so one lucky or unlucky answer cannot create fake certainty.

## Study-plan model

The current `heuristic-v3` planner combines:

1. **Course importance** from the topic graph.
2. **Exam weight** from past-paper frequency and known marks.
3. **Mastery gap** from measured diagnostic evidence, explicit overrides, or the fallback baseline.
4. **Mistake focus** from classified error patterns.

Mastery precedence is:

```text
explicit topic override
        ↓
measured diagnostic mastery
        ↓
fallback baseline mastery
```

Mistake burden slightly increases study priority and exposes `mistake_focus` on each topic allocation. It does not directly lower the projected grade because the underlying low-scoring response already affected mastery.

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
- [ ] automatic grading adapters
- [ ] spaced review / forgetting model
- [ ] mastery history and trend analytics

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

1. Create a course with a target grade.
2. Upload and process lectures and past papers.
3. Build the course topic graph with `/analyze`.
4. Build question-level exam intelligence.
5. Start a diagnostic and work through adaptive questions.
6. Score each response and optionally attach the student's answer, reference answer, feedback, and mistake labels.
7. Read measured mastery through `/mastery` and recurring error patterns through `/mistakes`.
8. Generate a study plan; StudyOS uses both mastery evidence and mistake focus when allocating time.

The next Phase 2 milestone is **automatic grading adapters + solution-grounded feedback**, followed by forgetting-aware review scheduling.