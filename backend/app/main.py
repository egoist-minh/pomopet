from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import sessions, tasks, chat, statistics, logs
from app.database.database import init_db
from app.utils.logger import app_logger, error_logger
import time

app = FastAPI(title="PomoPet Backend", version="0.1.0")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    app_logger.info(
        f"{request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Duration: {process_time:.2f}ms"
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(http://(localhost|127\.0\.0\.1)(:\d+)?)|(app://.*)",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

# Initialize database
@app.on_event("startup")
async def startup():
    await init_db()
    app_logger.info("=" * 50)
    app_logger.info("PomoPet Backend started")
    app_logger.info("=" * 50)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "message": str(exc)}
    )

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["statistics"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])

@app.get("/")
async def root():
    return {"message": "PomoPet Backend API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
