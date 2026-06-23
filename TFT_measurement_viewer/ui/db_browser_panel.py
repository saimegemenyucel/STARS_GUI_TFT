"""Database Browser: a tree view of everything stored in the shared database.

Shows wafers, ingested I-V sweeps grouped by die -> transistor (with their
metadata and any computed features), recipes (with steps), and yield metrics.
A Refresh button re-reads the database so changes made in the other GUIs appear.
"""

from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shared import db_browser
from shared.db import get_connection

logger = logging.getLogger(__name__)

_ROLE = Qt.ItemDataRole.UserRole


class DatabaseBrowserPanel(QWidget):
    """A refreshable tree browser over the shared SQLite database."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Summary"])
        self.tree.setColumnWidth(0, 320)
        self.tree.itemClicked.connect(self._on_item_clicked)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)

        self.summary = QLabel("—")
        self.summary.setStyleSheet("color:#9aa0aa;")
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)

        top = QHBoxLayout()
        top.addWidget(refresh_btn)
        top.addWidget(self.summary, stretch=1)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.tree)
        split.addWidget(self.detail)
        split.setSizes([560, 420])

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(split, stretch=1)

        self.refresh()

    # -- build --------------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the database and rebuild the tree."""
        self.tree.clear()
        self.detail.clear()
        conn = get_connection()
        try:
            counts = db_browser.table_counts(conn)
            wafers = db_browser.get_wafers(conn)
            sweeps = db_browser.get_sweeps(conn)
            recipes = db_browser.get_recipes(conn)
            yields = db_browser.get_yield_metrics(conn)
            steps_by_recipe = {
                int(r.recipe_id): db_browser.get_recipe_steps(conn, int(r.recipe_id))
                for r in recipes.itertuples()
            }
        finally:
            conn.close()

        self.summary.setText(
            f"{counts['wafers']} wafers · {counts['iv_sweeps']} sweeps · "
            f"{counts['iv_points']} points · {counts['recipes']} recipes · "
            f"{counts['tft_curve_features']} feature sets"
        )

        self._add_wafers(wafers, sweeps)
        self._add_recipes(recipes, steps_by_recipe)
        self._add_yields(yields)
        self.tree.expandToDepth(0)

    def _node(self, parent, text, summary="", detail=None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [text, summary])
        if detail is not None:
            item.setData(0, _ROLE, detail)
        return item

    def _add_wafers(self, wafers: pd.DataFrame, sweeps: pd.DataFrame) -> None:
        root = self._node(self.tree, f"Wafers ({len(wafers)})")
        # Group sweeps by their wafer so each wafer holds its own sweeps.
        by_wafer: dict = {}
        if sweeps is not None and not sweeps.empty:
            for wid, g in sweeps.groupby("wafer_id", dropna=False):
                key = None if (wid is None or (isinstance(wid, float) and pd.isna(wid))) else wid
                by_wafer[key] = g
        for w in wafers.itertuples():
            g = by_wafer.pop(w.wafer_id, None)
            n_sw = 0 if g is None else len(g)
            wnode = self._node(
                root, str(w.wafer_id),
                f"{w.process_node or ''} · {w.substrate_material or ''} · {n_sw} sweeps",
                detail={
                    "Wafer ID": w.wafer_id, "Name": w.wafer_name,
                    "Process node": w.process_node, "Substrate": w.substrate_material,
                    "Sweeps": n_sw, "Fabricated": w.fabrication_date,
                },
            )
            self._add_sweep_tree(wnode, g)
        # Sweeps whose wafer_id is not in the wafers table (or unassigned).
        for key, g in by_wafer.items():
            label = "(unassigned sweeps)" if key is None else f"{key} (no wafer row)"
            self._add_sweep_tree(self._node(root, label, f"{len(g)} sweeps"), g)

    def _add_sweep_tree(self, parent, sweeps) -> None:
        """Build the Die -> Transistor -> sweep sub-tree under a wafer node."""
        if sweeps is None or sweeps.empty:
            return
        for die, die_df in sweeps.groupby("die_col_row", dropna=False):
            die_node = self._node(parent, f"Die {die}", f"{len(die_df)} sweeps")
            for subdie, sub_df in die_df.groupby("subdie_col_row", dropna=False):
                tr_node = self._node(die_node, f"Transistor {subdie}",
                                     f"{len(sub_df)} sweeps")
                for s in sub_df.itertuples():
                    feat = ""
                    if pd.notna(getattr(s, "vth", None)):
                        feat = f" · Vth={s.vth:.2f} V, μ={s.mu_sat:.1f}"
                    self._node(
                        tr_node,
                        f"R{s.run_start} · {s.sweep_type}",
                        f"L{s.channel_length:g} W{s.channel_width:g} · "
                        f"{s.material_stack} · {s.runs} runs, {s.points} pts{feat}",
                        detail=self._sweep_detail(s),
                    )

    @staticmethod
    def _sweep_detail(s) -> dict:
        d = {
            "Source file": s.source_file, "Sweep type": s.sweep_type,
            "Run start": s.run_start, "Die": s.die_col_row,
            "Transistor": s.subdie_col_row,
            "Channel L (µm)": s.channel_length, "Channel W (µm)": s.channel_width,
            "Material stack": s.material_stack, "Instrument ch": s.instrument_ch,
            "Temperature (°C)": s.temperature_c, "Extra temp (°C)": s.extra_temp_c,
            "Runs": s.runs, "Points": s.points, "Imported": s.imported_at,
        }
        if pd.notna(getattr(s, "vth", None)):
            d["— computed features —"] = ""
            d["Vth (V)"] = round(float(s.vth), 3)
            d["μ_sat (cm²/Vs)"] = round(float(s.mu_sat), 2)
            d["SS (mV/dec)"] = round(float(s.ss_min), 1)
            d["On/Off"] = f"{float(s.on_off_ratio):.2e}"
        else:
            d["Computed features"] = "none yet (use Curve Analysis → Save to database)"
        return d

    def _add_recipes(self, recipes: pd.DataFrame, steps_by_recipe: dict) -> None:
        root = self._node(self.tree, f"Recipes ({len(recipes)})")
        for r in recipes.itertuples():
            r_node = self._node(
                root, str(r.recipe_name),
                f"{r.substrate_type or ''} · {r.target_process_node or ''} · "
                f"{int(r.step_count)} steps",
                detail={
                    "Recipe": r.recipe_name, "Substrate": r.substrate_type,
                    "Process node": r.target_process_node,
                    "Active": bool(r.is_active), "Description": r.description,
                    "Created": r.created_date, "Modified": r.last_modified_date,
                },
            )
            steps = steps_by_recipe.get(int(r.recipe_id))
            if steps is not None:
                for st in steps.itertuples():
                    self._node(
                        r_node, f"{st.step_order}. {st.process_name}",
                        f"{st.process_type} · {_g(st.temperature)}°C · {_g(st.duration)} min",
                        detail={
                            "Step": st.step_order, "Process": st.process_name,
                            "Type": st.process_type, "Temperature (°C)": st.temperature,
                            "Duration (min)": st.duration, "Pressure (mTorr)": st.pressure,
                            "Power (W)": st.power, "Gas mixture": st.gas_mixture,
                            "Notes": st.notes,
                        },
                    )

    def _add_yields(self, yields: pd.DataFrame) -> None:
        root = self._node(self.tree, f"Yield metrics ({len(yields)})")
        for y in yields.itertuples():
            self._node(
                root, str(y.wafer_id),
                f"{y.overall_yield_percentage:.1f}% · {y.functional_devices}/{y.total_devices}",
                detail={
                    "Wafer": y.wafer_id, "Yield %": y.overall_yield_percentage,
                    "Functional": y.functional_devices, "Total": y.total_devices,
                    "Defect density (/cm²)": y.defect_density_per_cm2,
                    "Dominant defect": y.dominant_defect_type,
                    "Calculated": y.calculation_timestamp,
                },
            )

    # -- detail -------------------------------------------------------------
    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        detail = item.data(0, _ROLE)
        if not isinstance(detail, dict):
            self.detail.clear()
            return
        rows = "".join(
            f"<tr><td style='color:#9aa0aa;padding-right:12px'>{k}</td>"
            f"<td><b>{'' if v is None else v}</b></td></tr>"
            for k, v in detail.items()
        )
        self.detail.setHtml(f"<table cellspacing='4'>{rows}</table>")


def _g(value) -> str:
    """Format an optional numeric value."""
    return "—" if value is None or pd.isna(value) else f"{value:g}"
