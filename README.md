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

## Current milestone — document intelligence foundation

The backend can now:

- create courses with exam dates and target grades
- persist course data in SQLite
- upload `.pdf`, `.docx`, `.pptx`, `.txt`, and `.md` study material
- stream uploads to disk and deduplicate them with SHA-256
- extract text from all supported document formats
- preserve PDF page and PowerPoint slide references
- store normalized source units and retrieval-ready text chunks
- deterministically classify common study-material types
- detect PDFs with too little extractable text and flag them for future OCR
- safely reprocess documents without duplicating extracted content
- expose extracted content without leaking internal storage paths

The extraction pipeline is deliberately deterministic and local-first. LLM-based concept extraction will be layered on top of source-grounded text instead of replacing the parsing layer.

### API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Service health |
| `POST` | `/api/v1/courses` | Create a course |
| `GET` | `/api/v1/courses` | List courses |
| `GET` | `/api/v1/courses/{course_id}` | Get one course |
| `POST` | `/api/v1/courses/{course_id}/documents` | Upload course material |
| `GET` | `/api/v1/courses/{course_id}/documents` | List uploaded material |
| `GET` | `/api/v1/courses/{course_id}/documents/{document_id}` | Get document metadata |
| `POST` | `/api/v1/courses/{course_id}/documents/{document_id}/process` | Extract and classify a document |
| `GET` | `/api/v1/courses/{course_id}/documents/{document_id}/content` | Read source units and chunks |

FastAPI also exposes interactive API documentation at `/docs` while the server is running.

## Source references

StudyOS keeps extracted content tied to its origin:

```text
PDF      -> page 1, page 2, ...
PPTX     -> slide 1, slide 2, ...
DOCX     -> document
TXT / MD -> document
```

Chunks inherit their source unit so later search, tutoring, topic extraction, and generated answers can cite the original material.

Scanned/image-only PDFs are currently flagged with `needs_ocr: true`; OCR itself is intentionally deferred to a later milestone.

## Roadmap

### Phase 1 — Course intelligence and planning
- [x] course model and persistence
- [x] document upload and metadata
- [x] PDF/DOCX/PPTX/TXT/MD text extraction
- [x] document chunking and source references
- [x] baseline document classification
- [ ] concept and topic extraction
- [ ] past-paper question structure extraction
- [ ] topic weighting and exam-frequency analysis
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
- LLM-assisted concept and exam analysis

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

## Example flow

Create a course:

```json
{
  "name": "Physics I",
  "exam_date": "2026-09-14",
  "target_grade": 25,
  "max_grade": 30
}
```

Upload a past paper or lecture deck, then call its `/process` endpoint. StudyOS will persist the extracted text with source references and return an analysis summary including document type, extracted character count, chunk count, and whether the file appears to need OCR.

The next milestone will use this source-grounded content to build the first **course topic graph** and **past-paper intelligence** layer.
