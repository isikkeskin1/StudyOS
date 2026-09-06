from __future__ import annotations

import os

import uvicorn

from app.main import app as studyos_app


def main() -> None:
    host = os.getenv("STUDYOS_DESKTOP_HOST", "127.0.0.1")
    port = int(os.environ["STUDYOS_DESKTOP_PORT"])
    uvicorn.run(
        studyos_app,
        host=host,
        port=port,
        log_level=os.getenv("STUDYOS_LOG_LEVEL", "warning").lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
