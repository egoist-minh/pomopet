from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import sessions, tasks, chat, statistics
from app.database.database import init_db

app = FastAPI(title="PomoPet Backend", version="0.1.0")

# CORS middleware for Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
@app.on_event("startup")
async def startup():
    await init_db()

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["statistics"])

@app.get("/")
async def root():
    return {"message": "PomoPet Backend API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
