# StudyOS

StudyOS is an AI-powered study planning platform that turns course materials into adaptive, evidence-driven study plans.

Upload lecture slides, notes, syllabi, exercise sheets, past exams, and solutions. StudyOS builds a structured model of the course, estimates what matters most for the exam, tracks student mastery, and recommends how to spend limited study time around a target grade.

> **Upload your course. Set your target grade. Let StudyOS determine the most efficient path to get there.**

## What StudyOS aims to answer

- What should I study next?
- How many focused hours should I invest?
- Which topics matter most for the exam?
- What grade is realistic with the time I have?
- How much time is likely required to reach my target?
- Which weak topics offer the highest expected improvement per hour?
- What should I deprioritize when time is running out?

## Current milestone — courses and source material

The backend can now:

- create courses with exam dates and target grades
- persist course data in SQLite
- upload `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md` study material
- stream uploads to disk instead of loading entire files into memory
- enforce configurable upload-size limits
- calculate SHA-256 hashes for source integrity and deduplication
- reject duplicate documents within a course
- expose document metadata without leaking internal storage paths
- run the API against isolated settings/databases for reliable tests

### API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create a course |
| `GET` | `/api/v1/courses` | List courses |
| `GET` | `/api/v1/courses/{course_id}` | Get one course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload course material |
| `GET` | `/api/v1/courses/{course_id}/documents` | List uploaded material |

FastAPI also exposes interactive API documentation at `/docs` while the server is running.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] course model and persistence
- [x] document upload and metadata
- [ ] PDF/DOCX/PPTX text extraction
- [ ] document chunking and source references
- [ ] concept and topic extraction
- [ ] past-paper classification
- [ ] topic weighting
- [ ] first study-plan engine

### Phase 2 — Diagnostics and mastery
Adaptive diagnostics, mastery tracking, mistake classification, and dynamic replanning.

### Phase 3 — Grade modelling
Expected-score ranges, target-grade probabilities, study-time simulations, and uncertainty tracking.

### Phase 4 — Course-aware tutor
Retrieval over uploaded material, cited explanations, exam-style questions, and guided problem solving.

### Phase 5 — Optimization
Expected marks per study hour, emergency mode, automatic rescheduling, and multi-course optimization.

### Phase 6 — Study operating system
Semester dashboard, spaced repetition, personalized cheat sheets, analytics, calendar integration, and PWA support.

## Architecture

```text
                    Web client
                        |
                        v
                     FastAPI
                /         |         \
               v          v          v
        PostgreSQL      Workers     Study Engine
                            |            |
                            v            v
                     Document Pipeline  Mastery Model
                            |            Grade Model
                            v            Scheduler
                  Parsing / Chunking     Optimizer
                            |
                            v
                    Retrieval Index
```

The current implementation uses SQLite and local file storage for zero-friction development. The boundaries are intentionally separated so persistence and object storage can later move to PostgreSQL/S3-compatible infrastructure without changing the public API.

## Tech stack

**Current**

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2
- SQLite
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
- LLM-assisted document analysis

## Local development

```bash
cd backend
python -m venv .venv
```

Activate the environment and install:

```bash
pip install -e ".[dev]"
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to use the API interactively.

Run checks:

```bash
ruff check .
pytest
```

## Example

Create a course:

```json
{
  "name": "Physics I",
  "exam_date": "2026-09-14",
  "target_grade": 25,
  "max_grade": 30
}
```

Then upload lecture slides, notes, or past papers to that course. The next milestone will turn those raw documents into structured text, concepts, and exam intelligence.
