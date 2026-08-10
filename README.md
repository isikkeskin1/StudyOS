<div align="center">

# 🧠 StudyOS

### Your course material in. A study operating system out.

**StudyOS turns your notes, slides, past papers, deadlines, grades, and actual performance into one adaptive system that tells you what to study next — and why.**

<br />

![Version](https://img.shields.io/badge/version-v0.51.0-7C3AED?style=for-the-badge)
![Status](https://img.shields.io/badge/status-BETA-F59E0B?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-ready-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br />

> ### Stop asking “what should I study?”
> Upload the course. Set the target. StudyOS builds the path.

</div>

---

## 🖥️ Download StudyOS for Windows

**StudyOS now ships as a desktop app.**

The Windows build bundles the production StudyOS interface **and a local FastAPI backend** into one desktop package. Normal users can install it and run StudyOS without installing Python, Node, Docker, or configuring a server.

### Windows downloads

When a GitHub Release is published, CI automatically attaches:

- **StudyOS Windows Installer** — normal NSIS setup wizard with Start Menu + desktop shortcut
- **StudyOS Portable** — run StudyOS without installing it

👉 **[Download the latest StudyOS release](https://github.com/isikkeskin1/StudyOS/releases/latest)**

On first launch, StudyOS starts a private local backend automatically and stores its SQLite database plus uploaded course files under your Windows AppData. Hosted/cloud mode remains optional; remote servers must use HTTPS.

> **Beta signing note:** current Windows beta binaries are unsigned, so Microsoft SmartScreen may display an “unknown publisher” warning. Code signing is planned before broad public distribution.

---

## ✨ What is StudyOS?

Most study apps give you a timer, a to-do list, or a chatbot.

**StudyOS is built to make decisions.**

It ingests your real course material, measures what you actually know, estimates where your marks are being lost, watches deadlines and forgetting, and continuously chooses the highest-value work available.

```text
📚 Course files + 📝 Past papers + 🎯 Target grade + ⏳ Time available
                              │
                              ▼
                    ┌───────────────────┐
                    │      StudyOS      │
                    │ Academic engine   │
                    └───────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
     🧠 Mastery          📈 Grade forecast    🔎 Weaknesses
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                    ⚡ Best next action
                              │
                              ▼
                 🔁 Measure → adapt → repeat
```

StudyOS does **not** assume that every topic deserves equal time. If one hour of Physics is expected to help your target more than one hour of Programming, it can prioritize Physics. If that changes after a practice session, the plan changes too.

---

## 🚀 The experience

| | You do | StudyOS does |
|---|---|---|
| **1 · Add courses** | Enter your subjects, grading scale, exam dates and target grades. | Creates the academic model for each course. |
| **2 · Upload material** | Drop in PDFs, DOCX, PPTX, TXT or Markdown. | Extracts, chunks, classifies and connects material to topics and evidence. |
| **3 · Measure yourself** | Complete diagnostics and practice. | Builds topic-level mastery, confidence, mistake and retention models. |
| **4 · Set your constraints** | Tell it how much time you actually have. | Calculates where each study block has the highest expected value. |
| **5 · Execute** | Follow the next action. | Tracks completion, updates evidence and rebuilds unfinished work when reality changes. |

---

## 🔥 What makes it different?

### 🎯 It optimizes for the grade you want

StudyOS models your **target gap**, not just generic “progress.”

A 25/30 target in Physics and an 80/100 target in Programming can compete for the same limited study time without incorrectly comparing raw marks across unrelated grading scales.

```text
Expected mark gain
        ×
Deadline pressure
        ×
Evidence confidence
        ↓
Value of the next study block
```

When a course reaches its projected target, StudyOS can stop allocating scarce time to it instead of manufacturing busywork.

### 🧠 It models what you actually know

Mastery is evidence-driven and topic-level. StudyOS combines diagnostics, practice attempts, mistakes, answer history, retention and evidence confidence instead of reducing an entire course to one progress bar.

**Built in:**
- adaptive diagnostics from course questions
- Bayesian topic mastery + confidence
- recurring mistake taxonomy
- response-level mastery history
- forgetting-aware effective mastery
- personalized learning and retention calibration
- exam-aware review queues
- spaced-repetition review sessions

### 📚 The tutor is grounded in your course

StudyOS can retrieve from your uploaded material using lexical, semantic or hybrid retrieval.

Tutor responses are validated for citation validity, contradictions, unsupported additions and numerical consistency. Practice supports hints, rubric-aware grading, session memory, remediation and source-linked solutions.

> The goal is not “AI that sounds confident.”  
> The goal is **answers you can trace back to the material you are studying.**

### ⚡ Emergency Mode

Exam tomorrow? Three chapters left? Five hours available?

Emergency Mode treats time as a hard constraint and greedily allocates blocks by expected marginal marks. The schedule is persistent: finishing early preserves time, finishing late consumes it, and replanning only rebuilds unfinished work.

### 🗓️ One semester, one control loop

StudyOS can optimize multiple courses under a **single shared time budget**.

```text
Physics ───────┐
Linear Algebra ├──► global optimizer ───► ordered study queue
Programming ───┘                              │
                                              ▼
                                      one next action
```

Deadlines continue counting down. Changed mastery, targets, grade settings and available time can trigger a new immutable queue revision while completed work stays in history.

### 📊 Forecasts with uncertainty

StudyOS does not pretend a grade forecast is certainty.

The probabilistic layer supports:
- score distributions and likely ranges
- target probabilities
- study-hour scenarios
- evidence-quality-driven uncertainty
- immutable pre-exam forecasts
- real-outcome comparison
- Brier score, log loss and interval coverage
- guarded empirical recalibration with held-out validation

---

## 🧩 Feature map

| Area | What StudyOS can do |
|---|---|
| 📥 **Course intelligence** | Ingest PDFs, DOCX, PPTX, TXT and Markdown; classify documents; extract topics and past-paper evidence |
| 🧠 **Mastery** | Diagnostics, topic mastery, confidence, mistakes, history, forgetting and personalized calibration |
| 📝 **Practice** | Adaptive questions, hints, rubric-aware grading, remediation and persistent practice sessions |
| 🔁 **Reviews** | Retention-aware due queues and persistent spaced-repetition sessions |
| 🤖 **Tutor** | Grounded search, citations, semantic/hybrid retrieval and claim validation |
| 📈 **Forecasting** | Grade projections, uncertainty, target probability and calibration |
| 🎯 **Planning** | Normal study plans, expected-marks optimization and target-aware stopping |
| 🚨 **Emergency Mode** | Hard-deadline optimization with persistent schedules and automatic replanning |
| 🌐 **Semester OS** | Cross-course optimization, persistent semester queues and command-center analytics |
| 📄 **Cheat sheets** | Source-grounded formulas, methods and recurring mistakes |
| 📅 **Calendar & focus** | Calendar-aware planning and focus workflow integration |
| 📲 **PWA** | Installable web app, offline shell and notifications |
| 🔐 **Account controls** | Account-scoped ownership, export and confirmed deletion |

---

## 🛡️ Built for a real beta, not just a demo

v0.50 is the **beta hardening release**.

The release includes:

🟣 account-scoped data ownership  
🔵 account export with sensitive-field redaction  
🟠 password + literal confirmation for destructive account deletion  
🟢 authentication abuse throttling and `Retry-After`  
🟡 expired-session cleanup  
🔴 CSP, HSTS and browser/API security headers  
⚪ production secret requirements  
🟤 database + writable-storage readiness checks  
🔷 non-root application containers  
🟪 migration, container, deployment and browser E2E gates

The current release audit is documented in [`docs/releases/v0.50.0-beta-audit.md`](docs/releases/v0.50.0-beta-audit.md).

---

## 🏗️ Architecture

```text
                         ┌────────────────────┐
                         │   Next.js Web/PWA  │
                         │   React 19 client  │
                         └─────────┬──────────┘
                                   │ same-origin /api
                                   ▼
                         ┌────────────────────┐
                         │      FastAPI       │
                         │ auth • courses • AI│
                         └──────┬───────┬─────┘
                                │       │
                    ┌───────────┘       └───────────┐
                    ▼                               ▼
          ┌──────────────────┐            ┌──────────────────┐
          │ PostgreSQL/SQLite│            │ Persistent files │
          │ academic state   │            │ course uploads   │
          └──────────────────┘            └──────────────────┘
                    │
                    ▼
          ┌──────────────────┐
          │ Intelligence     │
          │ mastery • plans  │
          │ retrieval • tutor│
          │ forecasts        │
          └──────────────────┘
```

### Stack

![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-D71F00?style=flat-square)
![Playwright](https://img.shields.io/badge/Playwright-E2E-2EAD33?style=flat-square&logo=playwright&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI-2088FF?style=flat-square&logo=githubactions&logoColor=white)

**Frontend:** Next.js 15 · React 19 · TypeScript 5.9 · PWA  
**Backend:** Python 3.12+ · FastAPI · Pydantic · SQLAlchemy 2  
**Data:** PostgreSQL in production · SQLite for local development/tests · persistent upload storage  
**Intelligence:** course extraction · retrieval · mastery · planning · forecasting · tutoring  
**Ops:** Docker Compose · GitHub Actions · Playwright · Ruff · Pytest

---

## 🧪 Quality gates

StudyOS is tested as a system, not only as isolated functions.

```text
Backend
├── Ruff
├── Alembic migration smoke
├── Pytest suite
└── Backend container build

Web
├── ESLint
├── TypeScript
├── PWA contract
├── Next.js production build
└── Web container build

Deployment
├── Docker Compose validation
├── Full stack startup
├── Readiness checks
├── Web topology
├── API through web proxy
└── Playwright browser E2E
```

---

## 💻 Run StudyOS locally

### Backend

```bash
git clone https://github.com/isikkeskin1/StudyOS.git
cd StudyOS/backend

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The API is then available locally and FastAPI exposes interactive API documentation at `/docs`.

### Web

Open another terminal:

```bash
cd StudyOS/web
npm install
npm run dev
```

The web app uses the local FastAPI backend through the configured Next.js rewrite.

---

## 🐳 Production-style Docker deployment

1. Copy the backend environment example and set a **long random** `POSTGRES_PASSWORD`.
2. Set `STUDYOS_ENV=production`, production URL/proxy settings and any provider credentials you intend to use.
3. Configure `STUDYOS_FORWARDED_ALLOW_IPS` for your trusted reverse proxy. Do not expose wildcard proxy trust outside the private Compose topology.
4. Configure a valid VAPID key pair if push notifications are enabled.
5. Validate and start:

```bash
docker compose config --quiet
docker compose up -d --build
```

6. Do not route beta traffic until both liveness and readiness are healthy.
7. Verify signup/login, onboarding, upload/processing, study flow, export and account deletion.
8. Require backend CI, web CI and deployment/browser smoke to pass before a release.

---

## 🗺️ Roadmap

| Phase | Status | Milestone |
|---|---|---|
| **1 · Course intelligence** | ✅ Complete | Source-aware ingestion, topic intelligence, past-paper weighting |
| **2 · Diagnostics & mastery** | ✅ Complete | Adaptive diagnostics, mistakes, retention, calibration |
| **3 · Grade modelling** | ✅ Complete | Probabilistic forecasts, outcomes and validation |
| **4 · Course-aware tutor** | ✅ Complete* | Grounded retrieval, practice, semantic reranking, claim validation |
| **5 · Optimization** | ✅ Complete | Expected-marks planning, Emergency Mode, multi-course optimization |
| **6 · Study operating system** | ✅ Complete | Semester queues, reviews, cheat sheets, calendar/focus, PWA |
| **v0.50 · Beta hardening** | ✅ Complete | Security, data controls, failure states, production readiness |
| **v0.51 · Desktop beta** | 🟣 Current | Windows installer, portable app, desktop distribution pipeline |

\*An external ANN/vector backend remains intentionally scale-driven rather than a beta requirement.

### What comes after v0.51?

The v0.5x line prioritizes **desktop beta feedback, regressions, reliability, compatibility and security** over throwing more feature surface into the product.

---

## ⚠️ Beta notes

StudyOS is currently a **beta**. Grade forecasts, expected mark gains and optimization scores are decision-support estimates — not guarantees of exam results.

OpenAI-backed functionality requires valid provider configuration. Core local workflows and CI do not require external provider credentials.

The current authentication rate limiter is process-local and appropriate for the current single-API-process topology. A shared/distributed limiter should replace it before horizontally scaling the API.

---

<div align="center">

## 🎓 Built around one question

### **“Given what I know, what I need, and how much time I have — what should I do next?”**

StudyOS exists to answer that question continuously.

<br />

**v0.51.0 Desktop Beta · Study smarter under real constraints.**

</div>
