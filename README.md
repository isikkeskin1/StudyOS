# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials and student performance into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, measures what matters most for the exam, tracks topic mastery, and recommends how to spend limited study time around a target grade.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS aims to answer

- What should I study next?
- How many focused hours should I invest?
- Which topics matter most for the exam?
- What grade is realistic with the time I have?
- How much time is likely required to reach my target?
- Which weak topics offer the highest expected improvement per hour?
- What should I deprioritize when time is running out?

## Current milestone — adaptive diagnostics and measured mastery

The backend can now:

- create courses with exam dates and target grades
- upload and deduplicate `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md` material
- extract source-aware text from supported document formats
- preserve PDF page and PowerPoint slide references
- classify common study-material types
- build a course-level topic graph with source evidence
- extract numbered past-paper questions and explicit mark values
- link exam questions to course topics
- calculate exam weights from mark share and question frequency
- estimate study hours required for a target grade
- generate per-topic study-time allocations with diminishing returns
- create adaptive diagnostic sessions from real past-paper questions
- choose each next diagnostic question using exam value, coverage, and mastery uncertainty
- keep returning the same unanswered question instead of silently skipping it
- record normalized scores, confidence, grading source, and response time
- update persistent topic mastery after every scored response
- use Bayesian priors so one lucky or unlucky answer cannot create fake certainty
- track mastery confidence separately from mastery itself
- automatically feed measured mastery back into the study planner
- preserve explicit per-topic mastery overrides when the user wants them

The planning engine is still a heuristic rather than a calibrated grade predictor. Diagnostic evidence now replaces baseline mastery where available, but future phases will calibrate learning rates and score distributions against observed performance.

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
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/responses` | Score a diagnostic response |
| `POST` | `/api/v1/courses/{course_id}/diagnostics/{session_id}/complete` | End a diagnostic early |
| `GET` | `/api/v1/courses/{course_id}/mastery` | Read measured topic mastery |
| `POST` | `/api/v1/courses/{course_id}/study-plan` | Generate a target-grade study plan |

FastAPI exposes interactive API documentation at `/docs` while the server is running.

## Mastery model

A diagnostic response is not treated as an absolute statement that a student either knows or does not know a topic. Each response contributes weighted evidence to every topic mapped to the source exam question.

Evidence strength currently considers:

1. topic relevance to the question
2. estimated question difficulty
3. response confidence
4. the normalized score from `0.0` to `1.0`

Topic mastery uses a Bayesian prior and reports a separate confidence value. Confidence rises as evidence accumulates, allowing the planner to distinguish between `70% mastery from one answer` and `70% mastery from repeated evidence`.

The diagnostic selector favors questions that are important in past exams, cover uncertain mastery, and avoid repeatedly testing the same topic when better coverage is available.

## Study-plan model

The current `heuristic-v2` planner combines:

1. **Course importance** from the topic graph.
2. **Exam weight** from past-paper question frequency and known marks.
3. **Mastery gap** from measured diagnostic evidence, explicit overrides, or the fallback baseline.

Mastery precedence is:

```text
explicit topic override
        ↓
measured diagnostic mastery
        ↓
fallback baseline mastery
```

Study hours are assigned incrementally to the topic with the highest marginal expected gain. Learning uses a diminishing-returns curve rather than assuming every extra hour is equally valuable.

Example request:

```json
{
  "available_hours": 20,
  "baseline_mastery": 0.5,
  "use_stored_mastery": true,
  "topic_mastery": {}
}
```

The response exposes `mastery_source` for every allocation so clients can see whether the estimate came from a diagnostic, an override, or the baseline.

## Source references

StudyOS keeps extracted content tied to its origin:

```text
PDF      -> page 1, page 2, ...
PPTX     -> slide 1, slide 2, ...
DOCX     -> document
TXT / MD -> document
```

Chunks inherit their source unit so later search, tutoring, topic extraction, and generated answers can cite the original material. Scanned/image-only PDFs are currently flagged with `needs_ocr: true` for a later OCR pipeline.

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
- [ ] mistake classification
- [ ] answer capture and automatic grading adapters
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
5. Start a diagnostic and score responses as the student works through questions.
6. Read measured mastery through `/mastery`.
7. Generate a study plan; StudyOS automatically uses the measured mastery where available.

The next Phase 2 milestone is **mistake classification + answer/grading infrastructure**, so StudyOS can learn not just which topics are weak, but *why* marks are being lost.
