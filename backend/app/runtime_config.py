import os
from pathlib import Path


DATA_DIR_ENV = "POMOPET_DATA_DIR"
HOST_ENV = "POMOPET_HOST"
PORT_ENV = "POMOPET_PORT"
RUNTIME_TOKEN_ENV = "POMOPET_RUNTIME_TOKEN"
PARENT_PID_ENV = "POMOPET_PARENT_PID"


def get_data_dir() -> Path:
    configured = os.getenv(DATA_DIR_ENV)
    if configured:
        data_dir = Path(configured).expanduser().resolve()
    else:
        data_dir = Path(__file__).resolve().parent.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_runtime_token() -> str:
    return os.getenv(RUNTIME_TOKEN_ENV, "")


def get_log_dir() -> Path:
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
