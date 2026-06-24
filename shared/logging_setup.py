"""Shared console + rotating-file logging setup for all three GUI modules.

Console output alone is lost as soon as a user closes the terminal, which
makes it hard to debug issues they report after the fact. Routing logs to a
file under the project root keeps the last few sessions around for that.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from shared.paths import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
BACKUP_COUNT = 3


def configure_logging(app_name: str, level: int = logging.INFO) -> None:
    """Configure the root logger with a console handler and a rotating file.

    Args:
        app_name: Used as the log file stem (e.g. "tft_measurement_viewer").
        level: Minimum level to log.
    """
    LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        LOG_DIR / f"{app_name}.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
