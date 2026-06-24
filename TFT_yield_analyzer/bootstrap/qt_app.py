"""Qt application entry point for the yield analyzer."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from TFT_yield_analyzer.bootstrap import config
from TFT_yield_analyzer.ui.main_window import MainWindow
from shared import init_database
from shared.logging_setup import configure_logging
from shared.style import DARK_STYLESHEET

logger = logging.getLogger(__name__)


def run() -> int:
    """Create the QApplication, show the main window and start the event loop."""
    configure_logging("tft_yield_analyzer")
    init_database()

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)
    if config.DARK_MODE_DEFAULT:
        app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()
