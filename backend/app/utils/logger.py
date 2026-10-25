import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
import json

from app.runtime_config import get_log_dir


LOG_DIR = get_log_dir()

LOG_FILE = LOG_DIR / "app.log"
ERROR_FILE = LOG_DIR / "error.log"
AUDIT_FILE = LOG_DIR / "audit.log"

MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def get_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    json_format: bool = False
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = JSONFormatter() if json_format else logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

app_logger = get_logger("pomopet", str(LOG_FILE))
error_logger = get_logger("pomopet.error", str(ERROR_FILE), logging.ERROR)
audit_logger = get_logger("pomopet.audit", str(AUDIT_FILE), logging.INFO, json_format=True)

class LoggerMixin:
    @property
    def logger(self):
        name = f"pomopet.{self.__class__.__name__}"
        return logging.getLogger(name)

def log_api_call(logger: logging.Logger, endpoint: str, method: str, **kwargs):
    audit_logger.info(f"API_CALL | {method} {endpoint} | {kwargs}")

def log_error(logger: logging.Logger, error: Exception, context: str = ""):
    error_logger.error(f"{context} | {type(error).__name__}: {str(error)}")
