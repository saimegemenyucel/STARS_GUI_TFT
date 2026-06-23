"""Qt application entry point for the measurement viewer."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from TFT_measurement_viewer.bootstrap import config
from TFT_measurement_viewer.ui.main_window import MainWindow
from shared import init_database
from shared.style import DARK_STYLESHEET

logger = logging.getLogger(__name__)


def run() -> int:
    """Create the QApplication, show the main window and start the event loop.

    Returns:
        The Qt application exit code.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    # Make sure the shared database exists before the UI queries it.
    init_database()

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)
    if config.DARK_MODE_DEFAULT:
        app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()
