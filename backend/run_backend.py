import argparse
import os
import threading
import time

import psutil


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PomoPet local backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    return parser.parse_args()


def require_loopback(host: str) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("PomoPet backend may only bind to a loopback address")


def watch_parent(parent_pid: int) -> None:
    while True:
        if not psutil.pid_exists(parent_pid):
            os._exit(0)
        try:
            parent = psutil.Process(parent_pid)
            if not parent.is_running() or parent.status() == psutil.STATUS_ZOMBIE:
                os._exit(0)
        except psutil.Error:
            os._exit(0)
        time.sleep(2)


def main() -> None:
    args = parse_args()
    require_loopback(args.host)

    os.environ["POMOPET_DATA_DIR"] = args.data_dir
    os.environ["POMOPET_PARENT_PID"] = str(args.parent_pid)

    if not os.getenv("POMOPET_RUNTIME_TOKEN"):
        raise ValueError("POMOPET_RUNTIME_TOKEN is required")

    threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=args.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
