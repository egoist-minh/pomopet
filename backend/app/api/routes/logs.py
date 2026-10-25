from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from typing import Optional
from datetime import datetime, timedelta
import re

from app.runtime_config import get_log_dir

router = APIRouter()

LOG_DIR = get_log_dir()

LOG_FILES = {
    "app": LOG_DIR / "app.log",
    "error": LOG_DIR / "error.log",
    "audit": LOG_DIR / "audit.log",
}

def parse_log_line(line: str) -> dict | None:
    patterns = [
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| ([^|]+):(\w+):(\d+) \| (.+)",
        r"(\d{4}-\d{2}-\d{2}T[\d:.]+Z?) \| (\w+) \| ([^|]+):(\w+):(\d+) \| (.+)",
    ]

    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            return {
                "timestamp": match.group(1),
                "level": match.group(2),
                "logger": match.group(3).strip(),
                "function": match.group(4),
                "line": int(match.group(5)),
                "message": match.group(6).strip(),
            }
    return None

@router.get("/")
async def get_logs(
    type: str = Query("app", enum=["app", "error", "audit"]),
    limit: int = Query(100, le=1000),
    level: Optional[str] = Query(None, enum=["DEBUG", "INFO", "WARNING", "ERROR"]),
    search: Optional[str] = None,
    since: Optional[str] = None,
):
    log_file = LOG_FILES.get(type)
    if not log_file or not log_file.exists():
        return {"logs": [], "message": f"Log file not found: {type}"}

    logs = []
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue

        parsed = parse_log_line(line)
        if not parsed:
            continue

        if level and parsed.get("level") != level:
            continue

        if search and search.lower() not in parsed.get("message", "").lower():
            continue

        if since:
            try:
                log_time = datetime.strptime(parsed["timestamp"], "%Y-%m-%d %H:%M:%S")
                since_time = datetime.strptime(since, "%Y-%m-%d")
                if log_time < since_time:
                    continue
            except ValueError:
                pass

        logs.append(parsed)

        if len(logs) >= limit:
            break

    return {"logs": logs, "count": len(logs)}

@router.get("/download")
async def download_log(
    type: str = Query("app", enum=["app", "error", "audit"]),
):
    log_file = LOG_FILES.get(type)
    if not log_file or not log_file.exists():
        return {"error": f"Log file not found: {type}"}

    return FileResponse(
        log_file,
        media_type="text/plain",
        filename=f"pomopet_{type}_{datetime.now().strftime('%Y%m%d')}.log"
    )

@router.get("/stats")
async def get_log_stats():
    stats = {}

    for name, log_file in LOG_FILES.items():
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0}
            for line in lines:
                for level in level_counts:
                    if f"| {level} |" in line:
                        level_counts[level] += 1

            stats[name] = {
                "total_lines": len(lines),
                "levels": level_counts,
                "size_bytes": log_file.stat().st_size,
            }
        else:
            stats[name] = {"total_lines": 0, "levels": {}, "size_bytes": 0}

    return {"stats": stats}

from pydantic import BaseModel

class FrontendLog(BaseModel):
    message: str
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status: Optional[int] = None
    error_code: Optional[str] = None
    request_id: Optional[str] = None
    retries: int = 0

@router.post("/frontend")
async def log_frontend_error(log: FrontendLog):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"{timestamp} | ERROR | frontend:api:0 | FRONTEND | "
        f"request_id={log.request_id or 'unknown'} error_code={log.error_code or 'unknown'} "
        f"status={log.status or 'unknown'} retries={log.retries} "
        f"method={log.method or 'GET'} endpoint={log.endpoint or ''} message={log.message}"
    )
    audit_log = LOG_FILES.get("audit")
    with open(audit_log, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
    return {"message": "Logged"}

@router.delete("/clear")
async def clear_logs(
    type: Optional[str] = Query(None, enum=["app", "error", "audit"]),
):
    if type:
        log_file = LOG_FILES.get(type)
        if log_file and log_file.exists():
            log_file.unlink()
            return {"message": f"Cleared log file: {type}"}
        return {"error": f"Log file not found: {type}"}

    for log_file in LOG_FILES.values():
        if log_file.exists():
            log_file.unlink()

    return {"message": "Cleared all log files"}
