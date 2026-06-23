"""A compact dark Qt stylesheet shared by all modules.

Kept intentionally simple: neutral greys with a single accent colour so the
three GUIs feel like one product.
"""

from __future__ import annotations

ACCENT = "#3d8bfd"

DARK_STYLESHEET = f"""
QWidget {{
    background-color: #1e1f26;
    color: #e6e6e6;
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 18px;
}}
QMainWindow, QDialog {{ background-color: #1a1b21; }}
QGroupBox {{
    border: 1px solid #34363f;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {ACCENT};
    font-weight: bold;
}}
QPushButton {{
    background-color: #2b2d36;
    border: 1px solid #3a3c46;
    border-radius: 5px;
    padding: 6px 12px;
}}
QPushButton:hover {{ background-color: #343742; }}
QPushButton:pressed {{ background-color: {ACCENT}; color: white; }}
QPushButton:disabled {{ color: #6a6a6a; border-color: #2a2a2a; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: #26272e;
    border: 1px solid #3a3c46;
    border-radius: 4px;
    padding: 4px;
}}
QComboBox::drop-down {{ border: none; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 26px; min-height: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    height: 15px;
    background-color: #313440;
    border-left: 1px solid #3a3c46;
    border-bottom: 1px solid #3a3c46;
    border-top-right-radius: 4px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    height: 15px;
    background-color: #313440;
    border-left: 1px solid #3a3c46;
    border-bottom-right-radius: 4px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background-color: {ACCENT}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 7px solid #e8e8e8;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 7px solid #e8e8e8;
}}
QHeaderView::section {{
    background-color: #2b2d36;
    color: #cfcfcf;
    padding: 5px;
    border: none;
    border-right: 1px solid #34363f;
    border-bottom: 1px solid #34363f;
}}
QTableView, QListWidget, QTreeWidget {{
    background-color: #22232a;
    alternate-background-color: #26272e;
    gridline-color: #34363f;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QTabBar::tab {{
    background: #26272e;
    padding: 6px 14px;
    border: 1px solid #34363f;
    border-bottom: none;
}}
QTabBar::tab:selected {{ background: {ACCENT}; color: white; }}
QStatusBar {{ background-color: #16171c; color: #9aa0aa; }}
QToolTip {{
    background-color: #2b2d36;
    color: #e6e6e6;
    border: 1px solid {ACCENT};
}}
"""

__all__ = ["DARK_STYLESHEET", "ACCENT"]
