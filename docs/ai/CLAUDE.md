# CLAUDE.md - PomoPet Development Guide
- **Response style: sacrifice grammar, keep clarity and accuracy.** Terse
  fragments over full sentences; drop articles and filler. Never compress at the
  cost of being understood or of being right — code, commit messages, error
  strings, security and destructive-action warnings stay written out in full.
- **Gloss every jargon term at first use, inline.** A term of art from outside
  this repo — `clean room`, `common prefix`, `prior art`, `computationally
  aware`, `causal`, `prefix decoding` — carries a short parenthetical
  explanation the first time it appears in a reply or a doc, right next to the
  word, not in a glossary further down and not left to context. Format:
  `` `common prefix` (phần đầu trùng nhau giữa hai lần decode) ``. Keep the
  original term verbatim — the gloss is added beside it, never a replacement,
  since the term is what's searchable in papers and issues. Repo-internal names
  (`_RunGate`, module 8, `StepEvent`) and standard acronyms (API, GPU, WER) need
  no gloss.
- **Think before coding.** State assumptions explicitly; if a request has
  several readings, present them instead of picking silently. Say so if a
  simpler approach exists, and stop and name what's confusing rather than
  guessing. **Ask for approval of the plan and assumptions before any big
  implementation.**
- **Simplicity first.** The minimum code that solves the problem: no features
  beyond what was asked, no abstractions for single-use code, no configurability
  nobody requested, no error handling for impossible scenarios.
- **Surgical changes.** Every changed line should trace directly to the request.
  Don't refactor, reformat or "improve" adjacent code; match existing style.
  Remove imports and helpers *your* change orphaned; mention pre-existing dead
  code rather than deleting it.
- **Goal-driven.** Turn the task into a verifiable goal ("fix the bug" → write a
  test that reproduces it, then make it pass), and for multi-step work state a
  short plan with a check per step.


## Project Overview

**PomoPet** is a desktop Pomodoro application with an AI pet companion (Pet Widget + Main Window) built with Electron + Next.js frontend and Python FastAPI backend.

- **Frontend**: Next.js 15 + React 19 + TypeScript + Tailwind CSS + Motion + Electron 33
- **Backend**: Python FastAPI + SQLAlchemy + SQLite + ChromaDB + OpenAI/Anthropic/Ollama
- **Data**: Local-only (SQLite + ChromaDB), no cloud sync in MVP
- **Architecture**: Multi-process — Electron wraps Next.js (static export), Python FastAPI runs at `http://localhost:8000`

## Conda Environment

Always use the `pomopet` conda environment when working with the backend:
```bash
conda activate pomopet
```

## Frontend Structure

```
frontend/
  app/                    # Next.js app router (page.tsx → DesktopEnvironment)
  components/
    DesktopEnvironment.tsx   # Root component: orchestrates Pet + MainWindow + state
    FloatingPet.tsx          # Draggable, always-on-top Pet widget with timer + emotions
    MainWindow.tsx           # Task management, chat, statistics, settings tabs
    SetupModal.tsx           # Initial setup (pet name, AI service)
  hooks/use-mobile.ts
  lib/
    api.ts               # API client with retry logic + TypeScript interfaces
    logger.ts            # Frontend logging utilities
    utils.ts             # Shared utilities
  main.js                # Electron entry (always-on-top, transparent, mouse passthrough)
  preload.js             # Electron preload bridge
```

## Backend Structure

```
backend/
  app/
    main.py              # FastAPI app entry with CORS + logging middleware
    api/routes/          # API routers: sessions, tasks, chat, statistics, logs
    models/models.py     # SQLAlchemy ORM models (Task, Session, Settings, Subtask)
    services/            # Business logic (SessionService, TaskService, AI, Statistics)
    database/database.py # SQLite + async session management
    utils/logger.py      # Backend logging
  requirements.txt       # Python deps (fastapi, sqlalchemy, chromadb, etc.)
  pomopet.db             # SQLite database (gitignored)
  .env.example           # Environment template
```

## Key Domain Language

Use these exact terms from `docs/ai/CONTEXT.md` — do NOT use alternatives:

| Canonical Term | Avoid |
|---|---|
| **Session** | Focus time, work period |
| **Task** | Work item, todo |
| **Subtask** | Sub-item, child task |
| **Pet** | Assistant, companion, buddy |
| **Distraction Chain** | Distraction streak, distraction count |
| **Statistics** | Analytics, metrics, insights |

## Session States

- `idle` → `running` → `paused` → `running` → `completed` / `cancelled`
- Distraction during Session → pause + penalty (+5 min) + increment Distraction Chain

## Pet Emotions & Triggers

- `happy`: Default during running Session
- `excited`: Session completed
- `worried`: Pause too long or deadline near
- `sad`: Session cancelled
- `sleepy`: During Break
- `thinking`: Processing chat message
- `angry`: User confirms distraction
- `idle`: Default / no session

## API Contracts

Base URL: `http://localhost:8000/api`

Key endpoints (see `lib/api.ts` for full list):
- `POST /api/sessions/start`, `/pause`, `/resume`, `/cancel`, `/extend`, `/distraction`
- `GET /api/sessions/current`, `/tasks/`
- `POST /api/tasks/`, `/tasks/{id}/complete`, `/tasks/subtasks`
- `GET /api/statistics/`, `/statistics/daily`, `/statistics/weekly`
- `POST /api/chat`

## Running the App

### Frontend only (dev)
```bash
cd frontend && npm run dev
```
Then in Electron (when backend ready):
```bash
npm run dev:native
```

### Backend only
```bash
conda activate pomopet
cd backend && python -m uvicorn app.main:app --reload
```

### Build Electron
```bash
cd frontend && npm run build
npm run build:native  # next build
```

## Code Conventions

- **Frontend**: TypeScript strict mode, `@/` path alias, Tailwind CSS v4, React functional components with hooks
- **State**: React context in `DesktopEnvironment.tsx`, prop drilling to `FloatingPet` + `MainWindow`
- **API client**: Centralized in `lib/api.ts` with retry logic (3 retries, exponential backoff)
- **Backend**: Async SQLAlchemy, service layer pattern, dependency injection via FastAPI `Depends`
- **Logging**: Use `app_logger` (info) and `error_logger` (errors) in backend
- **Naming**: camelCase for JS/TS, snake_case for Python

## Testing

- Backend: pytest with pytest-asyncio, in-memory SQLite (`:memory:`) for isolation
- Frontend: Manual testing for MVP; automated tests planned post-MVP

## Important Notes

- `backend/pomopet.db` is gitignored — do NOT commit
- Frontend uses `@/` alias pointing to project root
- Electron uses a small transparent, always-on-top Pet window plus a separate normal Main Window;
  state and actions are synchronized through the preload IPC bridge
- `isDev = false` in `main.js` — production mode uses `app://` protocol with `out/` directory
- Backend port is hardcoded to `8000` for MVP (see ADR for planned dynamic port allocation)
- No cloud sync, no authentication in MVP

## Documentation

- `docs/ai/CONTEXT.md` — Domain glossary and language rules
- `docs/ai/PRD.md` — Product requirements and architecture decisions
- `docs/ai/MVP.md` — MVP scope and roadmap
- `docs/ai/todolist.md` — Prioritized implementation work
- `docs/adr/` — Architecture Decision Records
