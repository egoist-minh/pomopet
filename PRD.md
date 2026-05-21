# PRD: PomoPet MVP - Desktop Pomodoro App with AI Pet Companion

## Problem Statement

Users struggle to maintain focus and productivity while working on tasks. Traditional Pomodoro apps are rigid and impersonal, lacking the emotional connection and personalized guidance that could help users stay motivated. Users need a companion that not only tracks their focus time but also understands their work patterns, provides encouragement, and helps them navigate distractions in a friendly, non-judgmental way.

## Solution

PomoPet is a desktop application that combines the Pomodoro technique with an AI pet companion. The Pet appears as a floating widget on the user's desktop with an expressive EMO-style digital face, providing visual feedback through emotions. Users can create tasks, start focus sessions with customizable durations, and receive guidance from their Pet through an AI-powered chat interface. The Pet helps users stay accountable while maintaining a warm, supportive presence throughout their workday.

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

### AI Chat & Guidance
35. As a user, I want to chat with my Pet about productivity, so that I can get personalized advice
36. As a user, I want to ask the Pet about focus techniques, so that I can learn better work habits
37. As a user, I want to ask the Pet about task prioritization, so that I can make better decisions about what to work on
38. As a user, I want to ask the Pet for motivation when I'm struggling, so that I can get encouragement
39. As a user, I want to ask the Pet about dealing with distractions, so that I can learn strategies to stay focused
40. As a user, I want the Pet to respond in a warm, friendly tone, so that interactions feel supportive rather than robotic
41. As a user, I want the Pet to show "thinking" emotion when processing my question, so that I know it's working
42. As a user, I want chat responses to be concise and actionable, so that I can quickly apply the advice

### Statistics & Insights
43. As a user, I want to see my total focus hours for today, so that I can track my daily productivity
44. As a user, I want to see how many Sessions I completed today, so that I can measure my progress
45. As a user, I want statistics to update in real-time, so that I always see current data

### Main Window & Navigation
46. As a user, I want to open a Main Window to manage Tasks and view statistics, so that I have a central place for app features
47. As a user, I want to switch between Tasks, Statistics, and Chat tabs, so that I can access different features easily
48. As a user, I want the Main Window to be separate from Pet Widget, so that I can close it without hiding my Pet
49. As a user, I want to reopen the Main Window from system tray, so that I can access it when needed

### Settings & Configuration
50. As a user, I want to configure my OpenAI API key, so that the Pet can chat with me
51. As a user, I want to customize my Pet's name during setup, so that it feels personal

### System Integration
52. As a user, I want the app to work on Windows, so that I can use it on my PC
53. As a user, I want all my data stored locally, so that my tasks and sessions remain private
54. As a user, I want the app to remember my Tasks between sessions, so that I don't lose my work

## Implementation Decisions

### Architecture
- **Hybrid architecture**: Electron + React frontend communicates with Python FastAPI backend via REST API and WebSocket
- **Rationale**: Documented in ADR-0001. Maintainer is proficient in Python for backend logic, while Electron provides cross-platform desktop capabilities and good animation support for Pet expressions
- **Communication**: REST API for CRUD operations, WebSocket for real-time Session timer updates and Pet emotion changes

### Frontend Modules

**PetWidget Component**
- Floating, draggable window (200x250px) with transparent background
- Always-on-top, frameless Electron window
- Displays Pet face (placeholder for Lottie animation) and timer
- Receives emotion updates via WebSocket from backend
- Receives timer updates (time_left, isRunning) via WebSocket
- Uses `-webkit-app-region: drag` for draggability

**SessionTimer Service**
- Manages Session state on frontend (syncs with backend)
- Formats time display (MM:SS)
- Listens to WebSocket events for timer updates
- Triggers UI updates when Session state changes

**TaskList Component**
- Displays all Tasks with priority color-coding (red=high, orange=medium, green=low)
- Form for creating new Task (name, priority dropdown, deadline date picker)
- Delete button per Task
- "Start" button per Task - prompts for duration, calls backend to start Session
- Fetches Tasks from backend on mount and after mutations

**ChatInterface Component**
- Message list (user messages right-aligned, Pet messages left-aligned)
- Input field and Send button
- Calls backend `/api/chat` endpoint
- Shows "Thinking..." indicator while waiting for response
- Scrolls to bottom on new messages

**MainWindow Component**
- Tab navigation (Tasks, Statistics, Chat)
- Renders active tab content
- Separate Electron window (800x600px, normal frame)
- Can be closed without affecting Pet Widget

**Statistics Display**
- Shows focus hours today (formatted to 1 decimal place)
- Shows number of completed Sessions today
- Fetches from backend `/api/statistics` on mount and periodically

### Backend Modules

**session_service (Deep Module)**
- **Interface**: `start_session(task_id, duration)`, `pause_session()`, `resume_session()`, `cancel_session()`, `extend_session(seconds)`, `get_current_session()`
- **Encapsulates**: Session lifecycle state machine (Running → Paused → Running, Running → Completed, Running → Cancelled), timer logic, validation
- **State transitions**: Only one active Session at a time; starting new Session cancels existing one
- **Returns**: Simple success/error messages and current Session state
- **Testable**: Pure business logic, no UI dependencies

**task_service (Deep Module)**
- **Interface**: `get_all_tasks()`, `create_task(task_data)`, `delete_task(task_id)`, `complete_task(task_id)`
- **Encapsulates**: Task CRUD operations, validation, database queries
- **Complete behavior**: For MVP, completing a Task deletes it (confirmed with user)
- **Returns**: Task list or success/error messages
- **Testable**: Database operations can be tested with in-memory SQLite

**ai_service (Deep Module)**
- **Interface**: `chat(message: str) -> str`
- **Encapsulates**: OpenAI API integration, system prompt management, error handling
- **System prompt**: Defines Pet personality as "Pomo, a friendly AI pet companion" focused on productivity advice
- **Configuration**: Uses OpenAI API key from environment variable
- **Returns**: String response from AI or error message
- **Testable**: Can mock OpenAI client for testing

**statistics_service (Deep Module)**
- **Interface**: `get_daily_statistics() -> dict`
- **Encapsulates**: Querying completed Sessions, calculating focus time, date filtering
- **Calculation**: Sums (duration - time_left) for all completed Sessions today, converts to hours
- **Returns**: `{focusHoursToday: float, sessionsCompleted: int}`
- **Testable**: Can seed database with test Sessions and verify calculations

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
distraction_count: Integer (default 0, for future use)
```

### API Contracts

**REST Endpoints**
- `POST /api/sessions/start` - Body: `{task_id, duration}` → Returns: `{id, message}`
- `POST /api/sessions/pause` → Returns: `{message}` or `{error}`
- `POST /api/sessions/resume` → Returns: `{message}` or `{error}`
- `POST /api/sessions/cancel` → Returns: `{message}`
- `POST /api/sessions/extend?minutes=X` → Returns: `{message}` or `{error}`
- `GET /api/sessions/current` → Returns: `{id, task_id, time_left, state}` or `null`
- `GET /api/tasks` → Returns: `[{id, name, priority, deadline}]`
- `POST /api/tasks` - Body: `{name, priority, deadline}` → Returns: `{id, message}`
- `DELETE /api/tasks/{id}` → Returns: `{message}` or `{error}`
- `POST /api/tasks/{id}/complete` → Returns: `{message}` (deletes Task)
- `POST /api/chat` - Body: `{message}` → Returns: `{message: response}`
- `GET /api/statistics` → Returns: `{focusHoursToday, sessionsCompleted}`

**WebSocket Events** (Future - not in MVP)
- `session:update` - Emitted every second during running Session with `{time_left, isRunning}`
- `pet:emotion` - Emitted when Pet emotion changes with emotion string

**Note**: For MVP, frontend will poll `/api/sessions/current` every second instead of WebSocket. WebSocket can be added post-MVP.

### Pet Emotions & Triggers
- **happy**: Default during running Session
- **excited**: When Session completes (state → completed)
- **sad**: When Session cancelled (state → cancelled)
- **thinking**: When processing chat message
- **sleepy**: During Break (future - not in MVP)

For MVP, emotions are represented as emoji placeholders. Lottie animations to be added later.

### Data Storage
- **SQLite database**: `pomopet.db` in app directory
- **Local-only**: No cloud sync in MVP
- **Initialization**: Database tables created automatically on first backend startup
- **Persistence**: Tasks and Sessions persist between app restarts

### Configuration
- **Backend**: `.env` file with `OPENAI_API_KEY`
- **Frontend**: No configuration needed for MVP (hardcoded backend URL: `http://127.0.0.1:8000`)

## Testing Decisions

### What Makes a Good Test
- **Test external behavior, not implementation**: Tests should verify what a module does (its interface), not how it does it (internal state, private methods)
- **Tests should be independent**: Each test should set up its own data and not depend on other tests
- **Tests should be deterministic**: Same input should always produce same output
- **Use real dependencies where practical**: For database tests, use in-memory SQLite rather than mocking the entire database layer

### Modules to Test

**session_service (High Priority)**
- Test Session lifecycle: start → pause → resume → complete
- Test Session lifecycle: start → cancel
- Test extending Session adds time correctly
- Test starting new Session cancels existing Session
- Test error cases: pause when no Session, resume when not paused
- Test state transitions are enforced correctly
- **Prior art**: None yet (new codebase), but follow pytest conventions with fixtures for database setup

**task_service (High Priority)**
- Test creating Task with all fields
- Test retrieving all Tasks
- Test deleting Task by ID
- Test completing Task removes it from database
- Test error case: delete non-existent Task
- **Prior art**: Similar to session_service tests, use pytest fixtures

**statistics_service (Medium Priority)**
- Test calculating focus hours from completed Sessions
- Test filtering Sessions by today's date
- Test handling empty database (no Sessions)
- Test multiple Sessions accumulate correctly
- **Prior art**: Similar to other service tests

**ai_service (Low Priority for MVP)**
- Test chat returns non-empty response (integration test with real API)
- Test error handling when API key is invalid
- Mock OpenAI client for unit tests to avoid API costs
- **Prior art**: Use pytest-mock or unittest.mock

### Testing Framework
- **Backend**: pytest with pytest-asyncio for async tests
- **Database**: Use in-memory SQLite (`:memory:`) for test isolation
- **Fixtures**: Create pytest fixtures for database session, sample Tasks, sample Sessions
- **Frontend**: Defer to post-MVP (React Testing Library would be used)

### Test Coverage Goals
- **Backend services**: Aim for 80%+ coverage of business logic
- **API routes**: Test happy paths for MVP, comprehensive error handling post-MVP
- **Frontend**: Manual testing for MVP, automated tests post-MVP

## Out of Scope

The following features are explicitly **not** included in this MVP and will be considered for future phases:

### Phase 2 Features (Distraction Management)
- App/website monitoring to detect when user switches to distracting apps
- Distraction detection and confirmation dialog
- Penalty system (adding 5 minutes to Session)
- Distraction Chain tracking
- Angry Pet emotion when user is distracted
- Weekly distraction statistics

### Phase 3 Features (Advanced Memory & Personalization)
- ChromaDB integration for long-term memory
- Pet remembering user's behavior patterns and personality
- Personalized reminder frequency and style
- AI suggesting Session duration based on Task and history
- Pet learning user's productive hours and distraction patterns

### Phase 4 Features (Enhanced Features)
- Subtask support (breaking Tasks into smaller pieces)
- Long Break (15-30 minutes after 4 Sessions)
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
- **Polling instead of WebSocket**: Frontend polls `/api/sessions/current` every second instead of real-time WebSocket updates. This is simpler for MVP but less efficient.
- **Emoji placeholders instead of Lottie animations**: Pet emotions shown as emoji text until Lottie animations are sourced/created
- **No authentication**: Single-user app, no login required
- **No data backup/export**: Users cannot export their data in MVP
- **No error recovery**: If backend crashes during Session, Session state is lost
- **No offline mode**: Backend must be running for app to work
- **Hardcoded backend URL**: Frontend assumes backend is at `http://127.0.0.1:8000`

## Further Notes

### Development Approach
- This is a "vibe code" project - maintainer prefers iterative, experimental development
- Focus on getting core features working before polish
- Use free Lottie animations from LottieFiles.com as placeholders for Pet expressions
- Prioritize backend stability (Python) since maintainer is most comfortable there

### Open Source Considerations
- Project will be open-sourced on GitHub
- Clear documentation (QUICKSTART.md, README.md) already created
- MIT license recommended for maximum adoption
- Contributors will need both Python and Node.js knowledge

### User Experience Priorities
- **Minimalism**: Keep UI simple to reduce cognitive load (per user's explicit request)
- **Emotional connection**: Pet should feel like a companion, not a tool
- **Flexibility**: Allow users to customize durations and skip features they don't need
- **Non-judgmental**: Pet should be supportive, not punishing (except for future distraction features)

### Technical Risks
- **Electron bundle size**: Electron apps are large (~150MB+). Acceptable for desktop app.
- **Python backend dependency**: Users must install Python and run backend separately. Consider packaging with PyInstaller post-MVP.
- **OpenAI API costs**: Users must provide their own API key and pay for usage. Consider adding local model support (Ollama) in Phase 3.
- **Cross-platform testing**: MVP developed on Windows. Mac/Linux testing needed before wider release.

### Success Metrics (Post-MVP)
- Users complete at least 3 Sessions per day
- Users chat with Pet at least once per day
- Users continue using app for 7+ consecutive days
- GitHub stars and community engagement
