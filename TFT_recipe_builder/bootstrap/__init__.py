"""Application bootstrap for the recipe builder.

qt_app is intentionally NOT imported here so the pure-logic modules that import
config/container do not transitively require PyQt6.
"""
