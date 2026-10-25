# PRD: PomoPet MVP - Desktop Pomodoro App with AI Pet Companion

## Problem Statement

Users need a desktop Pomodoro app with an AI pet to help maintain focus, track tasks, reduce distractions, and provide motivation via an interactive companion.

## Solution

An Electron-wrapped Next.js frontend provides the Pet Widget and Main Window. A local Python/FastAPI backend owns Session and Task state, Statistics, OpenAI chat, and SQLite persistence.

## User Stories

### Pet Widget & Presence
1. As a user, I want to see a Pet widget on my desktop, so that I have a constant visual reminder of my focus companion
2. As a user, I want to drag the Pet widget to any position on my screen, so that I can place it where it won't interfere with my work
3. As a user, I want the Pet widget to stay on top of other windows, so that I can always see my timer and Pet's expression
4. As a user, I want to minimize the Pet widget to system tray, so that I can hide it when needed without closing the app
5. As a user, I want to see the Pet's face with different emotions, so that I feel emotionally connected to my productivity companion
6. As a user, I want to see a timer displayed on the Pet widget, so that I know how much focus time remains
7. As a user, I want to name my Pet (or use default "Pomo"), so that it feels personalized to me

### Session Management
8. As a user, I want to start a focus Session by selecting a Task and duration, so that I can begin focused work
9. As a user, I want to choose my own Session duration, so that I can adapt the Pomodoro technique to my needs
10. As a user, I want to see the timer count down in real-time, so that I know how much time is left
11. As a user, I want to pause a running Session, so that I can handle urgent interruptions
12. As a user, I want to resume a paused Session, so that I can continue where I left off
13. As a user, I want to cancel a Session if needed, so that I can stop without completing it
14. As a user, I want to see a confirmation when my Session is about to end, so that I can decide what to do next
15. As a user, I want to choose to take a Break when Session ends, so that I can rest
16. As a user, I want to extend my Session when it ends, so that I can continue working if I'm in flow state
17. As a user, I want the Pet to show "happy" emotion during a running Session, so that I feel encouraged
18. As a user, I want the Pet to show "excited" emotion when I complete a Session, so that I feel rewarded
19. As a user, I want the Pet to show "sad" emotion when I cancel a Session, so that I'm gently reminded of my commitment

### Break Management
20. As a user, I want to take a Short Break (5 minutes) after completing a Session, so that I can rest briefly
21. As a user, I want to see the Pet in "sleepy/resting" emotion during Break, so that I'm reminded to relax
22. As a user, I want to customize Break duration, so that I can adjust rest time to my needs
23. As a user, I want to skip a Break and continue working, so that I have flexibility when I'm in flow
24. As a user, I want the timer to show Break countdown, so that I know when to return to work

### Task Management
25. As a user, I want to create a new Task with a name, so that I can track what I need to work on
26. As a user, I want to set a priority (high/medium/low) for each Task, so that I can organize by importance
27. As a user, I want to set a deadline for each Task, so that I can track time-sensitive work
28. As a user, I want to see all my Tasks in a list, so that I can review what needs to be done
29. As a user, I want to see Tasks color-coded by priority, so that I can quickly identify urgent work
30. As a user, I want to delete a Task, so that I can remove tasks I no longer need
31. As a user, I want to mark a Task as complete, so that I can track my progress
32. As a user, I want completed Tasks to be removed after confirmation, so that my list stays clean and focused on current work
33. As a user, I want to select a Task before starting a Session, so that my focus time is tied to specific work
34. As a user, I want to see which Task I'm currently working on during a Session, so that I stay oriented
35. As a user, I want to add subtasks to a task so I can break down work

### AI Chat & Guidance
36. As a user, I want to chat with my Pet about productivity, so that I can get personalized advice
37. As a user, I want to ask the Pet about focus techniques, so that I can learn better work habits
38. As a user, I want to ask the Pet about task prioritization, so that I can make better decisions about what to work on
39. As a user, I want to ask the Pet for motivation when I'm struggling, so that I can get encouragement
40. As a user, I want to ask the Pet about dealing with distractions, so that I can learn strategies to stay focused
41. As a user, I want the Pet to respond in a warm, friendly tone, so that interactions feel supportive rather than robotic
42. As a user, I want the Pet to show "thinking" emotion when processing my question, so that I know it's working
43. As a user, I want chat responses to be concise and actionable, so that I can quickly apply the advice

### Statistics & Insights
44. As a user, I want to see my total focus hours for today, so that I can track my daily productivity
45. As a user, I want to see how many Sessions I completed today, so that I can measure my progress
46. As a user, I want statistics to update in real-time, so that I always see current data
47. As a user, I want to view statistics of my focus time per day and distraction patterns so I can improve productivity
48. As a user, I want to see a distraction chain count per session and per week so I can monitor interruptions

### Main Window & Navigation
49. As a user, I want to open a Main Window to manage Tasks and view statistics, so that I have a central place for app features
50. As a user, I want to switch between Tasks, Statistics, and Chat tabs, so that I can access different features easily
51. As a user, I want the Main Window to be separate from Pet Widget, so that I can close it without hiding my Pet
52. As a user, I want to reopen the Main Window from system tray, so that I can access it when needed

### Settings & Configuration
53. As a user, I want to configure my OpenAI API key, so that the Pet can chat with me
54. As a user, I want to customize my Pet's name during setup, so that it feels personal
55. As a user, I want to configure which AI service (OpenAI, Claude, Ollama) powers the pet so I can use my preferred model

### System Integration
56. As a user, I want the app to work on Windows, so that I can use it on my PC
57. As a user, I want all my data stored locally, so that my tasks and sessions remain private
58. As a user, I want the app to remember my Tasks between sessions, so that I don't lose my work
59. As a user, I want the app to run offline with all data stored locally so I don't rely on an internet connection

### Additional Features
60. As a user, I want the pet to remind me to start a session when a deadline is approaching so I don't miss important work
61. As a user, I want the pet to detect distraction and apply a penalty (extra time) so I stay accountable
62. As a user, I want the pet to provide encouragement or advice based on my long‑term memory so I feel supported
63. As a user, I want the pet to display emotions (happy, excited, worried, sad, sleepy, thinking, angry) based on session state so I get affective feedback
64. As a user, I want to skip breaks or extend sessions when needed so I have flexibility

## Implementation Decisions

### Architecture
- **Frontend**: Next.js app (app/, components/, hooks/, lib/) — rewritten via AI vibe coding from the original Electron/React codebase
- **Backend**: Python FastAPI services for Session, Task, Statistics, and OpenAI chat
- **Desktop**: Electron loads the Next.js dev server in development and the static export in production
- **Data Storage**: SQLite (local) + ChromaDB (long‑term memory)
- **Communication**: REST API at `http://localhost:8000/api`

### Frontend Modules

**Frontend Core**
- Next.js app with `app/`, `components/`, `hooks/`, `lib/`
- State managed via React context and hooks

**Pet Widget (FloatingPet)**
- Floating, draggable component rendering animated pet and timer
- Receives emotion updates via context
- Handles clicks to open Main Window

**Session Manager**
- Logic for start/pause/resume/complete/cancel sessions
- Restores active Session state from the backend after reload
- Interfaces: `startSession(taskId)`, `pauseSession()`, `resumeSession()`, `endSession()`, `cancelSession()`

**Task Manager**
- CRUD for tasks and subtasks
- Interfaces: `createTask`, `updateTask`, `deleteTask`, `addSubtask`, `removeSubtask`

**Statistics**
- Computes focus time totals, daily breakdowns, distraction aggregates
- Queries local SQLite through the backend using the user's timezone offset

**Persistence Layer**
- Async SQLAlchemy over local SQLite with automatic, idempotent schema migration

**Settings**
- Pet name stored locally
- API keys entered in Settings are encrypted by Electron secure storage and held in backend memory; `.env` remains supported

### Backend Modules

**Backend API (FastAPI)**
- FastAPI routes and service layer for Session, Task, chat, logs, and Statistics

**AI Service**
- OpenAI and Gemini integration for concise productivity guidance
- Claude and Ollama remain out of scope for MVP

**Long‑Term Memory**
- ChromaDB integration for vectors
- Interfaces: `storeInteraction(text, metadata)`, `searchSimilar(query, limit)`

### Database Schema

**Task Table**
```
id: String (UUID, primary key)
name: String (not null)
priority: Enum(high, medium, low)
deadline: String (ISO date format)
created_at: DateTime
```

**Session Table**
```
id: String (UUID, primary key)
task_id: String (foreign key to Task)
duration: Integer (seconds)
time_left: Integer (seconds)
state: Enum(running, paused, completed, cancelled)
started_at: DateTime
completed_at: DateTime (nullable)
distraction_count: Integer (default 0)
```

### API Contracts

- `POST /api/sessions/start` — Body: `{task_id, duration}` → Returns: `{id, message}`
- `POST /api/sessions/pause` → Returns: `{message, time_left}`
- `POST /api/sessions/resume` → Returns: `{message, time_left}`
- `POST /api/sessions/cancel` → Returns: `{message}`
- `POST /api/sessions/complete` → Returns: `{message, duration}`
- `POST /api/sessions/extend` — Body: `{minutes}` → Returns: `{message, time_left, duration}`
- `GET /api/sessions/current` → Returns: `{id, task_id, time_left, state}` or `null`
- `GET /api/tasks` → Returns: `[{id, name, priority, deadline, estimatedDuration}]`
- `POST /api/tasks` — Body: `{name, priority, deadline, estimated_duration}` → Returns: `{id, message}`
- `DELETE /api/tasks/{id}` → Returns: `{message}`; missing IDs use HTTP 404
- `POST /api/tasks/{id}/complete` → Returns: `{message}` (deletes Task)
- `POST /api/chat` — Body: `{message, provider: "openai" | "gemini"}` → Returns: `{message: response}`
- `GET /api/statistics?timezone_offset=420` → Returns daily/weekly focus and distraction Statistics

### Pet Emotions & Triggers

- **happy**: Default during running Session
- **excited**: When Session completes (state → completed)
- **worried**: When pause is too long or deadline near
- **sad**: When Session cancelled (state → cancelled)
- **sleepy**: During Break
- **thinking**: When processing chat message
- **angry**: When user confirms distraction

### Data Storage

- **SQLite database**: `pomopet.db` in app directory (or `data/` for future Electron)
- **ChromaDB**: local vector store for long‑term memory
- **Local-only**: No cloud sync in MVP

### Configuration

- **Backend**: Runtime provider keys from the local UI, with `.env` fallback via `OPENAI_API_KEY` and `GEMINI_API_KEY`
- **Frontend**: Provider selection and secure API-key entry in Settings

## Testing Decisions

### What Makes a Good Test
- **Test external behavior, not implementation**: Tests should verify what a module does (its interface), not how it does it
- **Tests should be independent**: Each test should set up its own data and not depend on other tests
- **Tests should be deterministic**: Same input should always produce same output
- **Use real dependencies where practical**: For database tests, use in-memory SQLite rather than mocking the entire database layer

### Modules to Test

**Session Manager (High Priority)**
- Test Session lifecycle: start → pause → resume → complete
- Test Session lifecycle: start → cancel
- Test extending Session adds time correctly
- Test starting new Session cancels existing Session
- Test error cases: pause when no Session, resume when not paused

**Task Manager (High Priority)**
- Test creating Task with all fields
- Test retrieving all Tasks
- Test deleting Task by ID
- Test completing Task removes it from database
- Test error case: delete non-existent Task

**Statistics Service (Medium Priority)**
- Test calculating focus hours from completed Sessions
- Test filtering Sessions by today's date
- Test handling empty database (no Sessions)

**AI Service (Low Priority for MVP)**
- Test chat returns non-empty response (integration test with real API)
- Test error handling when API key is invalid
- Mock OpenAI client for unit tests to avoid API costs

### Testing Framework

- **Backend**: standard-library `unittest` with isolated async test cases
- **Database**: Use in-memory SQLite (`:memory:`) for test isolation
- **Frontend**: Node's built-in test runner for timer and API regression tests
- **Fixtures**: Each backend test creates an isolated in-memory database

### Test Coverage Goals

- **Backend services**: Aim for 80%+ coverage of business logic
- **API routes**: Test happy paths for MVP, comprehensive error handling post‑MVP
- **Frontend**: Automated regression tests for timer completion and backend failures

## Out of Scope

### Phase 2 Features (Distraction Management)
- App/website monitoring to detect when user switches to distracting apps
- Distraction detection and confirmation dialog
- Penalty system (adding 5 minutes to Session)
- Distraction Chain tracking
- Angry Pet emotion when user is distracted
- Weekly distraction statistics

### Phase 3 Features (Advanced Memory & Personalization)
- ChromaDB integration for long‑term memory (partial in MVP)
- Pet remembering user's behavior patterns and personality
- Personalized reminder frequency and style
- AI suggesting Session duration based on Task and history
- Pet learning user's productive hours and distraction patterns

### Phase 4 Features (Enhanced Features)
- Subtask support (partial in MVP)
- Long Break (15‑30 minutes after 4 Sessions)
- Detailed statistics (hourly breakdown, distraction patterns)
- Multiple AI service options (Claude, Ollama)
- Pet personality customization
- More complex Pet emotions and animations

### Phase 5 Features (Advanced Features)
- Cloud sync (optional)
- Export/import data
- Multiple Pet themes/appearances
- Sound effects and voice
- Mobile companion app
- Team/collaborative features

### Technical Debt Accepted for MVP
- **Periodic sync instead of WebSocket**: Frontend periodically writes remaining Session time to the backend
- **Emoji placeholders instead of Lottie animations**: Pet emotions shown as emoji text until Lottie animations are sourced/created
- **No authentication**: Single‑user app, no login required
- **No data backup/export**: Users cannot export their data in MVP
- **No offline mode**: Backend must be running for app to work
- **Hardcoded backend URL**: Frontend assumes backend is at `http://localhost:8000`

## Further Notes

### Development Approach
- This is a "vibe code" project — maintainer prefers iterative, experimental development
- Frontend and backend are integrated through the local REST API
- Focus on getting core features working before polish
- Use free Lottie animations from LottieFiles.com as placeholders for Pet expressions
- Prioritize backend stability (Python) since maintainer is most comfortable there

### Open Source Considerations
- Project will be open‑sourced on GitHub
- Clear documentation (QUICKSTART.md, README.md) already created
- MIT license recommended for maximum adoption
- Contributors will need both Python and Node.js knowledge

### User Experience Priorities
- **Minimalism**: Keep UI simple to reduce cognitive load (per user's explicit request)
- **Emotional connection**: Pet should feel like a companion, not a tool
- **Flexibility**: Allow users to customize durations and skip features they don't need
- **Non‑judgmental**: Pet should be supportive, not punishing (except for future distraction features)

### Technical Risks
- **Electron bundle size**: Electron apps are large (~150MB+). Acceptable for desktop app.
- **Python backend dependency**: Users must install Python and run backend separately. Consider packaging with PyInstaller post‑MVP.
- **OpenAI API costs**: Users must provide their own API key and pay for usage. Consider adding local model support (Ollama) in Phase 3.
- **Cross‑platform testing**: MVP developed on Windows. Mac/Linux testing needed before wider release.

### Success Metrics (Post‑MVP)
- Users complete at least 3 Sessions per day
- Users chat with Pet at least once per day
- Users continue using app for 7+ consecutive days
- GitHub stars and community engagement

### Additional Notes
- This PRD reflects the current state (frontend‑only Next.js implementation) and the near‑term plan to integrate backend and wrap with Electron.
- Updates to the PRD should be made as architectural decisions evolve (e.g., switching ORM, changing AI provider).
- The triage label `ready-for-agent` should be applied to the issue tracking this PRD so that autonomous agents can pick up implementation tasks.
