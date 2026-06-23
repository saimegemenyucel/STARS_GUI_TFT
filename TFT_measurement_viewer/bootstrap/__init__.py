"""Application bootstrap for the measurement viewer.

qt_app is intentionally NOT imported here so that the pure-logic modules
(which import config from this package) do not transitively require PyQt6.
Import run directly from TFT_measurement_viewer.bootstrap.qt_app.
"""
