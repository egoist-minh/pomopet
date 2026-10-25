import hmac
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import sessions, tasks, chat, statistics, logs, planning, proactive, relationship
from app.database.database import init_db
from app.services.agent_memory import agent_memory
from app.runtime_config import get_runtime_token
from app.utils.logger import app_logger, error_logger

app = FastAPI(title="PomoPet Backend", version="0.1.0")


@app.middleware("http")
async def authenticate_local_request(request: Request, call_next):
    token = get_runtime_token()
    if request.method != "OPTIONS" and token:
        supplied_token = request.headers.get("X-PomoPet-Token", "")
        if not hmac.compare_digest(supplied_token, token):
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "message": "Unauthorized local request",
                    "error_code": "UNAUTHORIZED",
                },
            )
    return await call_next(request)


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
    allow_origin_regex=r"(http://(localhost|127\.0\.0\.1)(:\d+)?)|(app://-)",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-PomoPet-Token", "X-Request-ID"],
    max_age=3600,
)

# Initialize database
@app.on_event("startup")
async def startup():
    await init_db()
    await agent_memory.start()
    app_logger.info("PomoPet Backend started")

@app.on_event("shutdown")
async def shutdown():
    await agent_memory.close()
    app_logger.info("PomoPet Backend stopped")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid4())
    error_logger.error(
        "Unhandled exception request_id=%s type=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "request_id": request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(uuid4())
    app_logger.warning("validation_error request_id=%s", request_id)
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Request validation failed",
            "error_code": "VALIDATION_ERROR",
            "request_id": request_id,
        },
    )

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["statistics"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(planning.router, prefix="/api/planning", tags=["planning"])
app.include_router(relationship.router, prefix="/api/relationship", tags=["relationship"])
app.include_router(proactive.router, prefix="/api/proactive", tags=["proactive"])

@app.get("/")
async def root():
    return {"message": "PomoPet Backend API"}


@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
