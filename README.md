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
- Can the tutor explain from my actual lectures, notes, exams, and solutions with exact citations?
- What should I deprioritize when time is running out?

## Current milestone — grounded external tutor synthesis

The backend is now at **v0.18.0**.

The course-aware tutor now supports both a deterministic offline provider and an optional OpenAI Responses API provider behind the same grounding contract:

```text
question
   ↓
course-isolated retrieval
   ↓
BM25 + course topic/evidence signal
   ↓
ranked citation packet
   ↓
local provider OR OpenAI provider
   ↓
local claim-to-citation verification
   ↓
supported answer OR refusal
```

The external model never receives unrestricted access to the course database. It receives only the already-ranked citation packet selected by StudyOS.

### Retrieval

Without a course topic graph, retrieval uses:

```text
lexical-bm25-v1
```

After course intelligence has been built, matching topic evidence becomes a second ranking signal:

```text
hybrid-topic-bm25-v1
```

Each result can expose:

```text
document_name
document_type
chunk_id
source_label
locator_type / locator_index
source_reference
excerpt
relevance_score
lexical_score
topic_affinity
term_coverage
matched_terms
matched_topics
```

References such as `lecture-slides.pptx — slide 4` and `exam.pdf — page 3` survive retrieval unchanged.

## Tutor synthesis providers

`POST /api/v1/courses/{course_id}/tutor/ask` accepts:

```text
provider: auto | local | openai
```

`auto` resolves to the deployment-level `STUDYOS_TUTOR_PROVIDER`. The default deployment provider is `local`, so development and CI remain deterministic and require no external credentials.

### Local provider

```text
local-grounded-v1
```

This provider is deterministic and extractive. It is useful as a test baseline and as a zero-cost fallback deployment mode.

### OpenAI provider

When explicitly configured, StudyOS can synthesize a richer explanation through the OpenAI Responses API. The default configured tutor model is:

```text
gpt-5.6-luna
```

The model name is environment-configurable and is never hard-coded into the API contract.

The provider sends:

```text
question
requested answer style
ranked source references
ranked source excerpts
```

It does **not** enable web search or external tools. API response storage is disabled for these requests.

Source excerpts are explicitly treated as untrusted data. The provider is instructed not to follow instructions found inside uploaded course text, reducing prompt-injection risk from documents.

Every substantive generated sentence must contain one or more inline citation markers such as `[1]` or `[1][2]`. If the citation packet is insufficient, the provider can return `INSUFFICIENT_EVIDENCE` and StudyOS refuses to synthesize an answer.

### Provider configuration

`.env.example` documents the supported settings:

```text
STUDYOS_TUTOR_PROVIDER=local
OPENAI_API_KEY=
STUDYOS_OPENAI_TUTOR_MODEL=gpt-5.6-luna
STUDYOS_OPENAI_TUTOR_MAX_OUTPUT_TOKENS=900
```

An explicit request for `provider: openai` without an API key returns `503`. Provider execution failures return `502`. StudyOS does not silently switch providers when an explicitly requested provider is unavailable.

## Grounding validation

Tutor answers now use:

```text
answer_mode: grounded-synthesis-v2
validation_model: citation-overlap-v2
```

The original validator only checked whether a sentence contained a syntactically valid citation marker. That is not enough: a model could append `[1]` to an unrelated sentence.

`citation-overlap-v2` therefore checks each substantive claim for:

1. at least one citation marker;
2. citation indices that exist in the retrieved packet;
3. meaningful token overlap with the cited excerpt;
4. at least two meaningful matching source terms for longer claims;
5. numerical values that also appear in the cited evidence.

A failed claim causes the whole generated draft to be rejected instead of partially returning unsupported text.

The response exposes:

```text
provider_requested
synthesis_provider
retrieval_model
retrieval_components
topic_signal_applied
grounding_status
validation_status
validation_model
citation_coverage
grounding_score
minimum_claim_support
validated_claim_count
unsupported_claim_count
```

This is still a conservative lexical grounding check, not a full natural-language-entailment system. A later verifier can replace it behind the same contract.

## Answer styles

Tutor requests can select:

```text
concise
guided
exam
```

The style is passed through the provider boundary without changing retrieval or grounding semantics.

## Tutor API

### Search course material

```text
POST /api/v1/courses/{course_id}/tutor/search
```

Example:

```json
{
  "query": "net force acceleration",
  "limit": 6,
  "document_types": ["lecture", "notes"]
}
```

### Ask from course material

```text
POST /api/v1/courses/{course_id}/tutor/ask
```

Offline/default example:

```json
{
  "question": "Why is acceleration negative in this solution?",
  "max_sources": 6,
  "minimum_relevance": 0.20,
  "answer_style": "guided",
  "provider": "auto"
}
```

Explicit external synthesis:

```json
{
  "question": "Why is acceleration negative in this solution?",
  "answer_style": "guided",
  "provider": "openai"
}
```

If evidence is insufficient, StudyOS returns `grounding_status: insufficient_evidence` rather than answering from unsupported general knowledge.

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
- answer capture and solution-grounded deterministic grading
- mistake taxonomy and recurring mistake analytics
- response-level mastery history and trends
- forgetting-aware effective mastery
- personalized learning responsiveness and retention calibration
- exam-aware review queue

### Planning and grade modelling

The `heuristic-v5` planner combines course importance, exam weight, forgetting-adjusted mastery, mistakes, personalized learning scale, and calibrated retention.

The `probabilistic-v1` layer adds expected score distributions, likely ranges, target probabilities, study-hour scenarios, and evidence-quality-driven uncertainty.

Forecast snapshots can later receive real exam outcomes. StudyOS measures MAE, RMSE, bias, interval coverage, Brier score, and log loss, then applies guarded `empirical-v1` recalibration only after enough outcomes exist.

Rolling-origin held-out validation tests whether recalibration improves forecasts it did not train on.

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
- [ ] richer rubric/LLM grading adapter

### Phase 3 — Grade modelling
- [x] probabilistic score distributions and target probabilities
- [x] immutable forecasts and real outcomes
- [x] empirical calibration/recalibration
- [x] reliability curves and rolling held-out validation

### Phase 4 — Course-aware tutor
- [x] deterministic course-isolated BM25 retrieval
- [x] exact page/slide/document citations
- [x] course topic/evidence retrieval signal
- [x] provider-neutral synthesis interface
- [x] deterministic local synthesis provider
- [x] optional OpenAI Responses API synthesis provider
- [x] prompt-injection-resistant source packet instructions
- [x] citation validity checks
- [x] claim-to-source lexical support validation
- [x] insufficient-evidence refusal
- [ ] embedding/vector retrieval adapter
- [ ] stronger semantic entailment verification
- [ ] exam-style question generation
- [ ] guided problem solving and hint progression
- [ ] personalization from mastery/mistake state

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

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, SQLite, OpenAI SDK, pypdf, python-docx, python-pptx, Pytest, Ruff, and GitHub Actions.

Planned infrastructure includes PostgreSQL, Redis/background workers, vector retrieval, Docker, and a Next.js/TypeScript client.

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

The next Phase 4 milestone is **semantic/vector retrieval plus exam-style question generation and guided hint progression over the same grounded citation packet**.
