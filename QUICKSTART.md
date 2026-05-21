# PomoPet - Quickstart Guide

## Prerequisites

- Node.js 18+ and npm
- Python 3.9+
- Git

## Setup

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "OPENAI_API_KEY=your_api_key_here" > .env

# Run backend
python -m app.main
```

Backend will run on http://127.0.0.1:8000

### 2. Frontend Setup

Open a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Run development mode
npm run dev
```

This will start both the React dev server and Electron app.

## Project Structure

```
pomopet/
├── frontend/              # Electron + React app
│   ├── src/
│   │   ├── main/         # Electron main process
│   │   ├── renderer/     # React app
│   │   └── preload/      # Preload scripts
│   └── package.json
├── backend/              # Python FastAPI
│   ├── app/
│   │   ├── api/         # API routes
│   │   ├── services/    # Business logic
│   │   ├── models/      # Database models
│   │   └── main.py      # Entry point
│   └── requirements.txt
├── docs/
│   └── adr/             # Architecture decisions
├── CONTEXT.md           # Domain glossary
├── MVP.md               # MVP roadmap
└── README.md
```

## Next Steps

1. **Get OpenAI API Key**: Sign up at https://platform.openai.com/
2. **Add Pet Animations**: Find Lottie animations at https://lottiefiles.com/
3. **Test the App**: Create a task and start a session
4. **Read Documentation**: Check CONTEXT.md and MVP.md

## Development

- Frontend hot-reloads on file changes
- Backend auto-reloads with uvicorn
- Database (SQLite) is created automatically on first run

## Troubleshooting

- **Backend won't start**: Check Python version and virtual environment
- **Frontend won't start**: Run `npm install` again
- **API errors**: Make sure backend is running on port 8000
- **Chat not working**: Check OPENAI_API_KEY in backend/.env
