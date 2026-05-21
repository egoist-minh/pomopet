# PomoPet Backend

Python FastAPI backend for PomoPet desktop app.

## Setup

1. Create virtual environment:
```bash
python -m venv venv
```

2. Activate virtual environment:
```bash
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```
OPENAI_API_KEY=your_api_key_here
```

5. Run the server:
```bash
python -m app.main
```

Server will run on http://127.0.0.1:8000

## API Endpoints

- `POST /api/sessions/start` - Start a new session
- `POST /api/sessions/pause` - Pause current session
- `POST /api/sessions/resume` - Resume paused session
- `POST /api/sessions/cancel` - Cancel current session
- `POST /api/sessions/extend` - Extend current session
- `GET /api/sessions/current` - Get current session info

- `GET /api/tasks` - Get all tasks
- `POST /api/tasks` - Create new task
- `DELETE /api/tasks/{id}` - Delete task
- `POST /api/tasks/{id}/complete` - Complete task

- `POST /api/chat` - Send message to AI
- `GET /api/statistics` - Get daily statistics
