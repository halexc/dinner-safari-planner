"""Desktop dinner safari workspace."""

import argparse
import json
import sys
from copy import deepcopy
from html import escape
from itertools import pairwise
from pathlib import Path

from geopy.distance import geodesic
from PySide6.QtCore import QElapsedTimer, QSettings, QSize, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPalette, QTextDocument
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .app_icon import application_icon, set_windows_app_id
from .collaboration import CollaborationSession, decode_snapshot, difference, resources, snapshot
from .collaboration_dialog import CollaborationDialog
from .data import (
    COURSES,
    CSV_REQUIRED,
    MODELS,
    STOP_FIELDS,
    DinnerData,
    Participant,
    Route,
    Stop,
    csv_source,
    demo_data,
    infer_csv_mapping,
    next_record_id,
    parse_csv,
    write_csv,
)
from .geocoding import AddressWorker
from .localization import (
    LANGUAGES,
    error_text,
    field_label,
    set_language,
    tr,
    translate_html,
    translate_message,
)
from .map_view import MAP_STYLES, STOP_OUTLINES, map_html
from .project import ProjectSettings, load_project, save_project
from .results import solution_summary, write_results
from .route_edit import MapBridge, RouteDraft
from .solver import SolverWorker
from .theme import course_icon, map_css, palette, stylesheet
from .verification import WARNING_TYPES, SegmentPreferences, route_signature, verify_route

STYLE = """
QMainWindow, QDialog { background: #f3f6f5; }
QWidget { color: #203c37; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#subtitle { color: #637a73; }
QLabel#section { font-size: 18px; font-weight: 600; }
QFrame#card { background: white; border: 1px solid #dbe5e0; border-radius: 12px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 12px 25px; margin: 0 6px 10px 0; background: #e7eeea; border-radius: 7px; }
QTabBar::tab:selected { background: #187f71; color: white; }
QPushButton { background: white; border: 1px solid #ccdbd4; border-radius: 6px; padding: 9px 14px; }
QPushButton:hover { background: #e5f2ec; border-color: #187f71; }
QPushButton:disabled { color: #95a59f; background: #f0f3f1; }
QPushButton#primary { background: #187f71; color: white; border: 0; }
QPushButton#primary:hover { background: #126759; }
QToolButton { background: white; border: 1px solid #ccdbd4; border-radius: 5px; padding: 5px; font-size: 18px; }
QToolButton:hover { background: #e5f2ec; border-color: #187f71; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: white; border: 1px solid #ccdbd4; border-radius: 5px; padding: 7px; }
QTableWidget, QListWidget, QTextBrowser { background: white; border: 1px solid #dbe5e0; border-radius: 7px; }
QTableWidget { alternate-background-color: #f5f8f6; gridline-color: #e6eee9; selection-background-color: #d6eee4; selection-color: #203c37; }
QHeaderView::section { background: #eaf0ed; padding: 12px 8px; border: 0; border-bottom: 1px solid #dbe5e0; font-weight: 600; }
QListWidget::item { padding: 0; border-bottom: 1px solid #edf2ef; }
QListWidget::item:selected { background: #d6eee4; color: #203c37; }
QSplitter::handle { background: #e0e9e4; }
QStatusBar { background: #eaf0ed; }
QSlider::groove:horizontal { height: 6px; background: #e7eeea; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #187f71; border-radius: 3px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #187f71; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: #95a59f; }
"""


def label(text: str, role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(True)
    return widget


def button(text: str, callback, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class GuestCellDelegate(QStyledItemDelegate):
    """Keep guest text for sorting/search while the links provide its rendering."""

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, styled, painter, option.widget)


class ReferenceLinks(QLabel):
    """Rich reference links that navigate only on a double click."""

    referenceActivated = Signal(str)

    def __init__(self, text):
        super().__init__(text)
        self.hovered_reference = ""
        self.linkHovered.connect(self.track_reference)
        self.setMouseTracking(True)

    def track_reference(self, reference):
        self.hovered_reference = reference

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.hovered_reference:
            self.referenceActivated.emit(self.hovered_reference)
        event.accept()


class RecordDialog(QDialog):
    def __init__(self, data: DinnerData, kind: str, record=None, parent=None):
        super().__init__(parent)
        self.data, self.kind, self.record = data, kind, record
        self.result_record = None
        self.setWindowTitle(f"{tr('Edit') if record else tr('Add')} {tr(kind[:-1])}")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        locked = (
            parent.collaboration.foreign_nodes()
            if parent and hasattr(parent, "collaboration")
            else {}
        )
        names = {
            "participants": ("id", "name", "address", "allergies", "latitude", "longitude"),
            "stops": ("id", "host", "guests", "course"),
            "routes": ("id", "appetizer_stop_id", "main_stop_id", "dessert_stop_id"),
        }[kind]
        titles = {
            "appetizer_stop_id": tr("Appetizer"),
            "main_stop_id": tr("Main Dish"),
            "dessert_stop_id": tr("Dessert"),
            "name": tr("Name / pairing"),
            "id": tr("ID"),
            "latitude": tr("Latitude (optional)"),
            "longitude": tr("Longitude (optional)"),
            "guests": tr("Guest IDs (comma-separated)"),
            "allergies": tr("Allergies (comma-separated)"),
        }
        values = record.model_dump() if record else {}
        if record is None:
            values["id"] = next_record_id(
                getattr(data, kind), {"participants": "P", "stops": "S", "routes": "R"}[kind]
            )
        for name in names:
            if kind == "routes" and name != "id":
                field = QComboBox()
                field.addItem(tr("Unassigned"), "")
                index = ("appetizer_stop_id", "main_stop_id", "dessert_stop_id").index(name)
                for stop in data.stops.values():
                    host = data.participants.get(stop.host)
                    eligible = host and data.route_stops(host.id)[index] in ("", stop.id)
                    if (
                        stop.host not in locked
                        and stop.course == COURSES[index]
                        and (
                            not getattr(parent, "safe_edit", True)
                            or eligible
                            or stop.id == values.get(name)
                        )
                    ):
                        field.addItem(
                            f"{stop.id} · {host.name if host else tr('Host unavailable')}", stop.id
                        )
                value = values.get(name, "")
                selected = field.findData(value)
                if selected < 0:
                    field.addItem(value, value)
                    selected = field.count() - 1
                field.setCurrentIndex(selected)
            elif name in ("host", "course"):
                field = QComboBox()
                if name == "course":
                    for course in COURSES:
                        field.addItem(tr(course), course)
                else:
                    field.addItem(tr("Unassigned"), "")
                    for p in data.participants.values():
                        if p.id in locked:
                            continue
                        field.addItem(f"{p.id} · {p.name}", p.id)
                value = values.get(name)
                if value:
                    index = field.findData(value)
                    if index < 0:
                        field.addItem(str(value), value)
                        index = field.count() - 1
                    field.setCurrentIndex(index)
            else:
                value = values.get(name)
                if isinstance(value, list):
                    value = ", ".join(value)
                field = QLineEdit("" if value is None else str(value))
                if name == "id":
                    field.setReadOnly(True)
                    field.setToolTip(tr("Automatically generated unique ID"))
            self.fields[name] = field
            form.addRow(titles.get(name, tr(name.title())), field)
        layout.addLayout(form)
        if kind == "participants":
            layout.addWidget(
                label(
                    tr(
                        "Coordinates place this host on the map. Leave them empty to use Find Addresses in Participants."
                    ),
                    "subtitle",
                )
            )
        self.error = label("")
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        actions.accepted.connect(self.save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    def save(self):
        values = self.record.model_dump() if self.record else {}
        for name, field in self.fields.items():
            if isinstance(field, QComboBox):
                values[name] = (
                    field.currentData()
                    if name in ("host", "course") or self.kind == "routes"
                    else field.currentText()
                )
            else:
                values[name] = field.text().strip()
        if self.kind == "participants":
            for name in ("latitude", "longitude"):
                values[name] = values[name] or None
            model, records = Participant, self.data.participants
        elif self.kind == "stops":
            values["guests"] = [
                value.strip() for value in values["guests"].split(",") if value.strip()
            ]
            model, records = Stop, self.data.stops
        else:
            model, records = Route, self.data.routes
        try:
            result = model(**values)
            if not self.record and result.id in records:
                raise ValueError(tr("ID {0} already exists.", f"{result.id}"))
            if self.kind == "stops":
                if result.host and result.host not in self.data.participants:
                    raise ValueError(tr("Select an existing host pairing."))
                unknown = set(result.guests) - self.data.participants.keys()
                if unknown:
                    raise ValueError(tr("Unknown guests: {0}", f"{', '.join(sorted(unknown))}"))
                if result.host in result.guests or len(result.guests) != len(set(result.guests)):
                    raise ValueError(tr("Guests must be unique and must not include the host."))
            self.result_record = result
            self.accept()
        except ValueError as error:
            self.error.setText(error_text(error))


class ParticipantPicker(QDialog):
    def __init__(self, data: DinnerData, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Select a pairing"))
        self.setMinimumWidth(480)
        self.resize(480, 450)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr("Pairings without a route"), "section"))
        self.participants = QListWidget()
        for participant in data.participants.values():
            if data.route_for(participant.id) is None:
                item = QListWidgetItem(
                    f"{participant.name}\n{participant.id} · {participant.address}"
                )
                item.setData(Qt.UserRole, participant.id)
                self.participants.addItem(item)
        layout.addWidget(self.participants, 1)
        if not self.participants.count():
            layout.addWidget(label(tr("All pairings already have course assignments."), "subtitle"))
        actions = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.select_button = actions.addButton(tr("Select"), QDialogButtonBox.AcceptRole)
        self.select_button.setEnabled(False)
        self.participants.currentItemChanged.connect(
            lambda item, _: self.select_button.setEnabled(item is not None)
        )
        self.participants.itemDoubleClicked.connect(lambda _: self.accept_selection())
        actions.accepted.connect(self.accept_selection)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    @property
    def participant_id(self):
        item = self.participants.currentItem()
        return item.data(Qt.UserRole) if item else None

    def accept_selection(self):
        if self.participant_id is not None:
            self.accept()


class CSVMappingDialog(QDialog):
    def __init__(self, path, kind, delimiter, parent=None):
        super().__init__(parent)
        self.path, self.kind = path, kind
        self.setWindowTitle(tr("Map CSV columns · {0}", tr(kind.title())))
        self.resize(850, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr("Choose how to import this CSV"), "section"))
        layout.addWidget(
            label(
                tr(
                    "Map each data column to a CSV column. Unmapped fields use their defaults. Missing or blank IDs are generated automatically."
                ),
                "subtitle",
            )
        )
        self.delimiter_combo = QComboBox()
        best_delimiter, best_score = delimiter, -1
        for title, separator in (
            (tr("Comma (,)"), ","),
            (tr("Semicolon (;)"), ";"),
            (tr("Tab"), "\t"),
            (tr("Pipe (|)"), "|"),
        ):
            self.delimiter_combo.addItem(title, separator)
            try:
                source = csv_source(path, separator)
                mapping, _ = infer_csv_mapping(source, kind)
                score = (
                    len(mapping)
                    + 5 * int(CSV_REQUIRED[kind].issubset(mapping))
                    - 10 * int(any(len(row) != len(source.headers) for _, row in source.rows))
                )
                if score > best_score or (score == best_score and separator == delimiter):
                    best_delimiter, best_score = separator, score
            except (OSError, ValueError):
                continue
        self.delimiter_combo.setCurrentIndex(self.delimiter_combo.findData(best_delimiter))
        delimiter_row = QHBoxLayout()
        delimiter_row.addWidget(label(tr("CSV delimiter")))
        delimiter_row.addWidget(self.delimiter_combo)
        delimiter_row.addStretch()
        layout.addLayout(delimiter_row)
        self.form_widget = QWidget()
        self.form = QFormLayout(self.form_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_widget)
        layout.addWidget(scroll, 1)
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.setMaximumHeight(180)
        layout.addWidget(label(tr("CSV preview (first five rows)"), "subtitle"))
        layout.addWidget(self.preview)
        self.error = label("", "error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Import"))
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.accepted.connect(self.confirm_mapping)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.column_combos = {}
        self.records = None
        self.delimiter_combo.currentIndexChanged.connect(self.populate)
        self.populate()

    def populate(self, *_):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.column_combos = {}
        self.error.setText("")
        try:
            self.source = csv_source(self.path, self.delimiter_combo.currentData())
        except (OSError, ValueError) as error:
            self.source = None
            self.preview.clear()
            self.error.setText(error_text(error))
            return
        mapping, _ = infer_csv_mapping(self.source, self.kind)
        titles = {
            "id": tr("ID (auto-generated if unmapped)"),
            "name": tr("Name / pairing"),
            "route_id": tr("Route ID"),
            "appetizer_stop_id": tr("Appetizer"),
            "main_stop_id": tr("Main Dish"),
            "dessert_stop_id": tr("Dessert"),
        }
        fields = list(MODELS[self.kind].model_fields)
        if self.kind == "participants":
            fields += [field for field in STOP_FIELDS if field in mapping]
        for field in fields:
            combo = QComboBox()
            combo.addItem(tr("Do not import (use default)"), None)
            for column, title in enumerate(self.source.headers):
                sample = next(
                    (
                        row[column]
                        for _, row in self.source.rows
                        if column < len(row) and row[column]
                    ),
                    "",
                )
                combo.addItem(
                    f"{column + 1}. {title or '(unnamed)'}"
                    + (f" — {sample[:55]}" if sample else ""),
                    column,
                )
                combo.setItemData(combo.count() - 1, sample, Qt.ToolTipRole)
            combo.setCurrentIndex(combo.findData(mapping[field]) if field in mapping else 0)
            self.column_combos[field] = combo
            self.form.addRow(titles.get(field, field_label(field)), combo)
        self.preview.clear()
        self.preview.setColumnCount(len(self.source.headers))
        self.preview.setHorizontalHeaderLabels(self.source.headers)
        self.preview.setRowCount(min(5, len(self.source.rows)))
        for row_index, (_, row) in enumerate(self.source.rows[:5]):
            for column, value in enumerate(row[: len(self.source.headers)]):
                self.preview.setItem(row_index, column, QTableWidgetItem(value))
        self.preview.resizeColumnsToContents()

    def confirm_mapping(self):
        if self.source is None:
            return
        try:
            self.records = parse_csv(
                self.source,
                self.kind,
                mapping={field: combo.currentData() for field, combo in self.column_combos.items()},
            )
        except ValueError as error:
            self.error.setText(error_text(error))
            return
        self.accept()


class PenaltySlider(QSlider):
    """Smooth fractional multipliers, represented as integer thousandths."""

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setRange(0, 5000)
        self.setValue(1000)
        self.setSingleStep(1)
        self.setPageStep(100)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setValue(1000)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class SolverPreview(QDialog):
    def __init__(
        self, result, preferences, ignored_warnings, parent=None, *, respect_existing_routes=False
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Review generated routes"))
        self.resize(1100, 650)
        layout = QVBoxLayout(self)
        data = result.data
        diagnostics = {
            pid: verify_route(data, pid, preferences, ignored_warnings) for pid in data.participants
        }
        warnings = sum(len(d["warnings"]) for d in diagnostics.values())
        active = {sid for route in data.routes.values() for sid in route.stops}
        sizes = [1 + len(data.stops[sid].guests) for sid in active]
        layout.addWidget(label(translate_message(result.message), "section"))
        layout.addWidget(
            label(
                tr(
                    "{0} complete routes · {1} active stops · {2} warnings · group sizes {3}–{4} pairings · {5} seconds",
                    f"{len(data.routes)}",
                    f"{len(active)}",
                    f"{warnings}",
                    f"{min(sizes)}",
                    f"{max(sizes)}",
                    f"{result.elapsed:.1f}",
                ),
                "subtitle",
            )
        )
        layout.addWidget(
            label(
                tr("Distances are straight-line estimates. ")
                + (
                    tr(
                        "Apply keeps assigned stops, completes incomplete routes and assigns remaining participants; guest lists are updated."
                    )
                    if respect_existing_routes
                    else tr(
                        "Apply replaces all route assignments and guest lists; participants and stop records are kept."
                    )
                ),
                "subtitle",
            )
        )
        if max(sizes) - min(sizes) > 1:
            layout.addWidget(
                label(tr("Warning: Active stop group sizes differ by more than one pairing."))
            )
        table = QTableWidget(len(data.participants), 6)
        table.setHorizontalHeaderLabels(
            [
                tr("Participant"),
                *[tr(course) for course in COURSES],
                tr("Distance (km)"),
                tr("Warnings"),
            ]
        )
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, (pid, participant) in enumerate(data.participants.items()):
            stops = [data.stops[sid] for sid in data.route_stops(pid)]
            points = data.coordinates(pid)
            distance = sum(geodesic(a, b).km for a, b in pairwise(points))
            values = [
                participant.name,
                *(data.participants[stop.host].name for stop in stops),
                f"{distance:.2f}",
                str(len(diagnostics[pid]["warnings"])),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (1, 2, 3):
                    stop = stops[column - 1]
                    item.setToolTip(f"{stop.id} · {data.participants[stop.host].address}")
                elif column == 5:
                    item.setToolTip(
                        "\n".join(tr(message) for message in diagnostics[pid]["warnings"])
                        or tr("No warnings")
                    )
                else:
                    item.setToolTip(pid if column == 0 else tr("Straight-line estimate"))
                table.setItem(row, column, item)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr("Apply routes"))
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Discard"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(
        self, data: DinnerData | None = None, *, enable_map: bool = True, preferences=None
    ):
        super().__init__()
        self.data = data or DinnerData()
        self.setWindowIcon(application_icon())
        self.enable_map = enable_map
        self.verified = False
        self.dirty = False
        self.collaboration = CollaborationSession(self)
        self.syncing_collaboration = False
        self.collaboration_client_joined = False
        self.map_reload_serial = 0
        self.collaboration.state_received.connect(self.receive_collaboration_state)
        self.collaboration.status_changed.connect(self.update_collaboration_controls)
        self.collaboration.locks_changed.connect(self.refresh_collaboration_locks)
        self.collaboration.failed.connect(self.collaboration_error)
        self.project_path = None
        self.exported = set()
        self.draft = None
        self.pending_pairing = None
        self.focus_selected_route = False
        self.route_diagnostics = {}  # participant ID -> {warnings: [...], errors: [...]}
        self.segment_preferences = SegmentPreferences()
        self.ignored_warnings = set()
        self.warning_multipliers = dict.fromkeys(WARNING_TYPES, 1.0)
        self.minimize_warning_counts = dict.fromkeys(WARNING_TYPES, True)
        self.respect_existing_routes = False
        self.verification_signatures = {}
        self.preferences = (
            preferences
            if preferences is not None
            else QSettings("Cykelfest", "DinnerSafariPlanner")
        )
        self.dark_mode = self.preferences.value("system/dark_mode", False, type=bool)
        self.verify_on_change = self.preferences.value("system/verify_on_change", False, type=bool)
        self.map_style = self.preferences.value("system/map_style", "standard")
        if self.map_style not in MAP_STYLES:
            self.map_style = "standard"
        self.safe_edit = True
        self.address_worker = None
        self.solver_worker = None
        self.closing_after_solve = False
        try:
            self.solver_maximum_time = max(
                1, min(3600, int(self.preferences.value("system/solver_maximum_time", 30)))
            )
        except (TypeError, ValueError):
            self.solver_maximum_time = 30
        self.closing_after_lookup = False
        self.csv_delimiter = self.preferences.value("system/csv_delimiter", ",")
        if self.csv_delimiter not in (",", ";", "\t", "|"):
            self.csv_delimiter = ","
        self.language = self.preferences.value("system/language", "en")
        if self.language not in LANGUAGES:
            self.language = "en"
        set_language(self.language)
        QApplication.instance().setApplicationName(tr("Cykelfest"))
        self.build_workspace()

    def build_workspace(self):
        self.setWindowTitle(tr("Cykelfest · Dinner safari planner"))
        self.resize(1400, 900)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(STYLE)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 12)
        heading = QHBoxLayout()
        intro = QVBoxLayout()
        intro.addWidget(label(tr("Cykelfest"), "title"))
        subtitle = label(tr("Good food. New company. A ride between every course."), "subtitle")
        subtitle.setWordWrap(False)
        intro.addWidget(subtitle)
        heading.addLayout(intro)
        heading.addStretch()
        self.counts = label("")
        self.counts.setWordWrap(False)
        heading.addWidget(self.counts)
        from .theme import group_icon

        self.collaborate_button = QPushButton(tr("Collaborate"))
        self.collaborate_button.clicked.connect(self.open_collaboration)
        self.collaborate_button.setIcon(group_icon())
        self.collaborate_button.setIconSize(QSize(20, 20))
        self.collaborate_button.setStyleSheet(
            "QPushButton { background: #b9e3f7; color: #164b68; border: 1px solid #83c8e9; }"
            "QPushButton:hover { background: #a3d9f2; border-color: #5fb4df; }"
            "QPushButton:pressed { background: #8dceed; }"
        )
        self.new_project_button = button(tr("New Project"), self.new_project)
        self.save_project_button = button(tr("Save Project"), self.save_project, self.dirty)
        self.load_project_button = button(tr("Load Project"), self.load_project)
        heading.addWidget(self.collaborate_button)
        heading.addWidget(self.new_project_button)
        heading.addWidget(self.save_project_button)
        heading.addWidget(self.load_project_button)
        self.export_results_button = button(tr("Export results"), self.export_results)
        heading.addWidget(self.export_results_button)
        layout.addLayout(heading)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_map_tab()
        self.tables = {}
        self.data.ensure_routes()
        for kind in ("participants", "stops", "routes"):
            self.build_data_tab(kind)
        self.build_settings_tab()
        self.setCentralWidget(root)
        self.apply_theme(self.dark_mode)
        self.update_collaboration_controls()
        if self.verify_on_change:
            self.verify_routes()

    def build_settings_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(tr("Settings"), "section"))
        layout.addWidget(
            label(
                tr(
                    "System preferences stay on this computer. Project settings travel with your .dsf file."
                ),
                "subtitle",
            )
        )
        content = QWidget()
        sections = QHBoxLayout(content)
        sections.setContentsMargins(0, 0, 0, 0)
        sections.setSpacing(16)
        left_sections = QVBoxLayout()
        right_sections = QVBoxLayout()
        sections.addLayout(left_sections, 1)
        sections.addLayout(right_sections, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.dark_mode_toggle = QCheckBox(tr("Enabled"))
        self.dark_mode_toggle.setChecked(self.dark_mode)
        self.verify_change_toggle = QCheckBox(tr("Enabled"))
        self.verify_change_toggle.setChecked(self.verify_on_change)
        self.safe_edit_toggle = QCheckBox(tr("Enabled"))
        self.safe_edit_toggle.setChecked(self.safe_edit)
        self.respect_routes_toggle = QCheckBox(tr("Enabled"))
        self.respect_routes_toggle.setChecked(self.respect_existing_routes)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.delimiter_combo = QComboBox()
        self.osm_combo = QComboBox()
        for key, (title, _, _) in MAP_STYLES.items():
            self.osm_combo.addItem(tr(title), key)
        self.osm_combo.setCurrentIndex(self.osm_combo.findData(self.map_style))
        self.solver_time_control = QSpinBox()
        self.solver_time_control.setRange(1, 3600)
        self.solver_time_control.setSuffix(" s")
        self.solver_time_control.setValue(self.solver_maximum_time)
        self.minimum_segment = QDoubleSpinBox()
        self.maximum_segment = QDoubleSpinBox()
        for control, value in (
            (self.minimum_segment, self.segment_preferences.minimum_km),
            (self.maximum_segment, self.segment_preferences.maximum_km),
        ):
            control.setRange(0, 1000)
            control.setDecimals(2)
            control.setSingleStep(0.1)
            control.setSuffix(" km")
            control.setValue(value)
        self.minimum_segment.setMaximum(self.segment_preferences.maximum_km)
        self.maximum_segment.setMinimum(self.segment_preferences.minimum_km)
        for title, delimiter in (
            (tr("Comma (,)"), ","),
            (tr("Semicolon (;)"), ";"),
            (tr("Tab (\\t)"), "\t"),
            (tr("Pipe (|)"), "|"),
        ):
            self.delimiter_combo.addItem(title, delimiter)
        self.delimiter_combo.setCurrentIndex(self.delimiter_combo.findData(self.csv_delimiter))
        entries = (
            (
                tr("Safe Edit"),
                self.safe_edit_toggle,
                tr(
                    "Allow only hosts who are home or unassigned for the edited course. Ineligible map stops stay visible at 25% opacity and are excluded from course dropdowns. Disable to allow every host at full opacity. Changes still require Save."
                ),
            ),
            (
                tr("Preferred minimum segment length (km)"),
                self.minimum_segment,
                tr(
                    "Warn when a segment is shorter than this distance. A soft constraint for automatic route generation. Uses straight-line estimates until cycling paths are available."
                ),
            ),
            (
                tr("Preferred maximum segment length (km)"),
                self.maximum_segment,
                tr(
                    "Warn when a segment is longer than this distance. Automatic generation treats this as a soft bound and forbids distances over three times this value; verification reports them as errors. Uses straight-line estimates until cycling paths are available."
                ),
            ),
            (
                tr("Dark Mode"),
                self.dark_mode_toggle,
                tr(
                    "Switch between the light and dark GUI. The map visualization is selected separately below. Saved on this computer."
                ),
            ),
            (
                tr("OSM-data"),
                self.osm_combo,
                tr(
                    "Choose the OpenStreetMap-based background visualization. Requires internet access for map tiles. Saved on this computer independently of GUI dark mode."
                ),
            ),
            (
                tr("Verify on Change"),
                self.verify_change_toggle,
                tr(
                    "Automatically verify after data edits, imports, route saves and map draft changes. Turn off to run verification only with Verify all routes. Draft verification does not save your edits."
                ),
            ),
            (
                tr("CSV-Delimiter"),
                self.delimiter_combo,
                tr(
                    "Choose the separator used for importing and exporting all three CSV tables. Select the delimiter used by the file before importing. Quoted names and guest lists are preserved."
                ),
            ),
            (
                tr("Maximum solver time"),
                self.solver_time_control,
                tr(
                    "Maximum time for preparing and optimizing an automatic assignment, in seconds (default 30). A valid result can be reviewed even if optimality is not proven. Saved on this computer, outside .dsf projects."
                ),
            ),
            (
                tr("Localization"),
                self.language_combo,
                tr(
                    "Choose the interface language. Saved on this computer; project files and CSV field names are unchanged."
                ),
            ),
        )
        for section_title, section_entries in (
            (tr("System"), entries[3:]),
            (
                tr("Project Settings"),
                entries[:3]
                + (
                    (
                        tr("Respect existing routes"),
                        self.respect_routes_toggle,
                        tr(
                            "Keep every existing route ID and assigned stop unchanged during generation. Fill empty slots and assign participants without routes. Invalid or conflicting assigned stops prevent generation. Other participants can join existing stops. Saved with the project."
                        ),
                    ),
                ),
            ),
        ):
            card = QFrame()
            card.setObjectName("card")
            form = QFormLayout(card)
            form.setContentsMargins(24, 18, 24, 18)
            form.setSpacing(14)
            form.addRow(label(section_title, "section"))
            for title, control, description in section_entries:
                self.add_setting_row(form, title, control, description)
            left_sections.addWidget(card)
        left_sections.addStretch()
        self.warning_toggles = {}
        self.warning_minimization_toggles = {}
        self.warning_sliders = {}
        self.warning_multiplier_labels = {}
        card = QFrame()
        card.setObjectName("card")
        warning_layout = QVBoxLayout(card)
        warning_layout.setContentsMargins(24, 18, 24, 18)
        warning_layout.setSpacing(20)
        warning_layout.addWidget(label(tr("Project Warnings"), "section"))
        warning_layout.addWidget(
            label(
                tr(
                    "Ignore hides a warning. Penalties range from 0 to 5; double-click a slider to reset to 1. Errors are always reported."
                ),
                "subtitle",
            )
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(20)
        for column, title in enumerate(
            ("Warning type", "Ignore", "Autogen: Minimize #Warnings", "Penalty multiplier")
        ):
            heading = label(tr(title))
            heading.setStyleSheet("font-weight: 600;")
            if column in (1, 2):
                heading.setAlignment(Qt.AlignCenter)
            grid.addWidget(heading, 0, column)
        grid.setColumnStretch(0, 1)
        for index, warning in enumerate(WARNING_TYPES, 1):
            toggle = QCheckBox()
            toggle.setChecked(warning in self.ignored_warnings)
            self.warning_toggles[warning] = toggle
            toggle.setAccessibleName(tr("Ignore") + ": " + tr(warning))
            toggle.setToolTip(
                tr(
                    "Ignore the warning '{0}' during verification. Saved with the project.",
                    tr(warning),
                )
            )
            minimize = QCheckBox()
            minimize.setChecked(self.minimize_warning_counts[warning])
            minimize.setAccessibleName(tr("Autogen: Minimize #Warnings") + ": " + tr(warning))
            minimize.setToolTip(
                tr(
                    "Include this warning in the first optimization objective. Turning this off keeps penalty scoring and verification unchanged. Saved with the project."
                )
            )
            self.warning_minimization_toggles[warning] = minimize
            slider = PenaltySlider()
            slider.setValue(round(self.warning_multipliers[warning] * 1000))
            slider.setEnabled(warning not in self.ignored_warnings)
            slider.setMinimumWidth(80)
            slider.setMaximumWidth(120)
            slider.setToolTip(
                tr(
                    "Solver penalty multiplier (0–5). Zero removes this penalty without hiding the warning. Double-click to reset to 1. Ignored warnings always have zero solver penalty."
                )
            )
            self.warning_sliders[warning] = slider
            value_label = label(f"{self.warning_multipliers[warning]:.3f}×")
            value_label.setFixedWidth(65)
            self.warning_multiplier_labels[warning] = value_label
            controls = QWidget()
            row = QHBoxLayout(controls)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            row.addWidget(slider, 1)
            row.addWidget(value_label)
            warning_label = label(tr(warning).removesuffix("."))
            warning_label.setToolTip(toggle.toolTip())
            grid.addWidget(warning_label, index, 0)
            grid.addWidget(toggle, index, 1, Qt.AlignCenter)
            grid.addWidget(minimize, index, 2, Qt.AlignCenter)
            grid.addWidget(controls, index, 3)
            minimize.toggled.connect(self.warning_minimization_changed)
            toggle.toggled.connect(self.warning_preferences_changed)
            toggle.toggled.connect(lambda ignored, control=slider: control.setEnabled(not ignored))
            slider.valueChanged.connect(
                lambda value, name=warning: self.warning_multiplier_changed(name, value)
            )
        warning_layout.addLayout(grid)
        right_sections.addWidget(card)
        right_sections.addStretch()
        self.dark_mode_toggle.toggled.connect(self.apply_theme)
        self.verify_change_toggle.toggled.connect(self.set_verify_on_change)
        self.safe_edit_toggle.toggled.connect(self.set_safe_edit)
        self.delimiter_combo.currentIndexChanged.connect(
            lambda _: setattr(self, "csv_delimiter", self.delimiter_combo.currentData())
        )
        self.osm_combo.currentIndexChanged.connect(self.set_map_style)
        self.tabs.addTab(page, tr("Settings"))
        self.minimum_segment.valueChanged.connect(self.segment_preferences_changed)
        self.maximum_segment.valueChanged.connect(self.segment_preferences_changed)
        for control in (self.dark_mode_toggle, self.verify_change_toggle):
            control.toggled.connect(self.system_settings_changed)
        self.delimiter_combo.currentIndexChanged.connect(self.system_settings_changed)
        self.osm_combo.currentIndexChanged.connect(self.system_settings_changed)
        self.solver_time_control.valueChanged.connect(self.set_solver_time)
        self.language_combo.currentIndexChanged.connect(self.change_language)
        self.safe_edit_toggle.toggled.connect(self.project_settings_changed)
        self.respect_routes_toggle.toggled.connect(self.set_respect_routes)
        self.minimum_segment.valueChanged.connect(self.project_settings_changed)
        self.maximum_segment.valueChanged.connect(self.project_settings_changed)

    def add_setting_row(self, form, title, control, description):
        heading = QWidget()
        row = QHBoxLayout(heading)
        row.setContentsMargins(0, 0, 16, 0)
        title_label = label(title)
        title_label.setToolTip(description)
        row.addWidget(title_label)
        hint = label("?")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setFixedSize(24, 24)
        hint.setToolTip(description)
        row.addWidget(hint)
        row.addStretch()
        control.setToolTip(description)
        form.addRow(heading, control)

    def system_settings_changed(self, *_):
        for key in (
            "dark_mode",
            "verify_on_change",
            "csv_delimiter",
            "map_style",
            "solver_maximum_time",
            "language",
        ):
            self.preferences.setValue(f"system/{key}", getattr(self, key))
        self.preferences.sync()

    def change_language(self, *_):
        language = self.language_combo.currentData()
        if language == self.language:
            return
        if self.solver_worker is not None or self.address_worker is not None:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
            self.language_combo.blockSignals(False)
            self.statusBar().showMessage(
                tr(
                    "Wait until address lookup or route generation finishes before changing the language."
                )
            )
            return
        selected, tab = self.selected_route, self.tabs.currentIndex()
        size = self.size()
        map_mode, show_hosts = self.map_mode.currentData(), self.show_hosts.isChecked()
        records = {kind: self.selected_record(kind) for kind in self.tables}
        searches = {kind: search.text() for kind, (_, search) in self.tables.items()}
        self.language = language
        self.system_settings_changed()
        set_language(language)
        QApplication.instance().setApplicationName(tr("Cykelfest"))
        self.build_workspace()
        self.resize(size)
        self.map_mode.setCurrentIndex(self.map_mode.findData(map_mode))
        self.show_hosts.setChecked(show_hosts)
        if self.project_path:
            self.setWindowTitle(tr("{0} · Cykelfest", self.project_path.name))
        self.refresh(selected)
        if self.draft:
            self.set_editing(True)
        for kind, text in searches.items():
            self.tables[kind][1].setText(text)
            table = self.tables[kind][0]
            for row in range(table.rowCount()):
                if table.item(row, 0).data(Qt.UserRole) == records[kind]:
                    table.selectRow(row)
        self.tabs.setCurrentIndex(tab)

    def set_solver_time(self, seconds):
        self.solver_maximum_time = seconds
        self.system_settings_changed()

    def set_map_style(self, *_):
        self.map_style = self.osm_combo.currentData()
        if self.enable_map:
            _, tiles, attribution = MAP_STYLES[self.map_style]
            self.map.page().runJavaScript(
                "(() => { const layer = window.cykelfestBaseLayer; const map = window.cykelfestMap;"
                "if (!layer || !map) return; map.attributionControl.removeAttribution(layer.options.attribution);"
                f"layer.options.attribution = {json.dumps(attribution)};"
                "map.attributionControl.addAttribution(layer.options.attribution);"
                f"if (layer._url !== {json.dumps(tiles)}) layer.setUrl({json.dumps(tiles)}); }})();"
            )

    def project_settings_changed(self, *_):
        if not self.syncing_collaboration and self.collaboration.mode == "host":
            self.sync_collaboration()
        self.set_project_dirty(True)

    def open_collaboration(self):
        if self.draft or self.address_worker or self.solver_worker:
            self.statusBar().showMessage(
                tr("Finish route editing or background work before collaborating.")
            )
            return
        CollaborationDialog(self).exec()

    def collaboration_error(self, message):
        QMessageBox.warning(self, tr("Collaborate"), tr(message))

    def update_collaboration_controls(self):
        if not hasattr(self, "collaborate_button"):
            return
        active = self.collaboration.mode in ("host", "client")
        client = self.collaboration.mode == "client"
        if self.collaboration.mode == "offline":
            self.collaboration_client_joined = False
        self.collaborate_button.setText(tr("Collaborating...") if active else tr("Collaborate"))
        self.collaborate_button.setStyleSheet(
            "QPushButton { background: #74bde4; color: #164b68; border: 1px solid #4c9ecb; }"
            if active
            else "QPushButton { background: #b9e3f7; color: #164b68; border: 1px solid #83c8e9; }"
        )
        editing = self.draft is not None
        if self.collaboration.mode == "offline" and not editing:
            for index in (1, 2, 3):
                self.tabs.setTabEnabled(index, True)
        for control in (
            self.new_project_button,
            self.load_project_button,
            self.export_results_button,
            self.clear_routes_button,
            self.generate_routes_button,
            self.pre_gen_button,
            self.find_addresses_button,
            *getattr(self, "host_only_controls", []),
        ):
            control.setEnabled(
                not client
                and not editing
                and self.address_worker is None
                and not self.collaboration.locks
            )
        self.export_results_button.setEnabled(not client and not editing)
        for control in (
            self.safe_edit_toggle,
            self.respect_routes_toggle,
            self.minimum_segment,
            self.maximum_segment,
            *self.warning_toggles.values(),
            *self.warning_minimization_toggles.values(),
            *self.warning_sliders.values(),
        ):
            control.setEnabled(not client and not self.collaboration.locks)
        for warning, slider in self.warning_sliders.items():
            slider.setEnabled(
                not client and not self.collaboration.locks and warning not in self.ignored_warnings
            )
        if not editing:
            self.add_route_button.setEnabled(not (client and self.collaboration.busy))
            self.edit_route_button.setEnabled(
                bool(self.selected_route) and not (client and self.collaboration.busy)
            )
            self.remove_route_button.setEnabled(
                bool(self.selected_route) and not (client and self.collaboration.busy)
            )
        foreign = self.collaboration.foreign_nodes()
        if self.selected_route:
            hosts = [
                self.data.stops[sid].host
                for sid in self.data.route_stops(self.selected_route)
                if sid in self.data.stops
            ]
            if self.selected_route in foreign or any(host in foreign for host in hosts):
                self.edit_route_button.setEnabled(False)
                self.remove_route_button.setEnabled(False)
            for index, (_, _, edit) in enumerate(self.course_controls):
                stop = self.data.stops.get(self.data.route_stops(self.selected_route)[index])
                edit.setEnabled(
                    self.selected_route not in foreign and (not stop or stop.host not in foreign)
                )

    def refresh_collaboration_locks(self):
        self.update_collaboration_controls()
        if hasattr(self, "map"):
            if self.draft:
                self.map_bridge.publish(self.draft)
            else:
                self.refresh_map()

    def receive_collaboration_state(self, state):
        initial = self.collaboration.mode == "client" and not self.collaboration_client_joined
        if self.syncing_collaboration or (
            not initial and snapshot(self.data, self.project_settings()) == state
        ):
            return
        selected, tab, draft = self.selected_route, self.tabs.currentIndex(), self.draft
        searches = {kind: search.text() for kind, (_, search) in self.tables.items()}
        data, settings = decode_snapshot(state)
        self.syncing_collaboration = True
        try:
            path = (
                self.project_path
                if self.collaboration.mode == "host" or self.collaboration_client_joined
                else None
            )
            self.collaboration_client_joined = self.collaboration.mode == "client"
            self.apply_project(data, settings, path)
            if draft and draft.participant_id in data.participants:
                hosts = [draft.host_at(i) for i in range(3)]
                rebuilt = RouteDraft(data, draft.participant_id, safe_edit=self.safe_edit)
                rebuilt.session = draft.session
                for i, host in enumerate(hosts):
                    if host != rebuilt.host_at(i):
                        rebuilt.replace(i, host) if host else rebuilt.remove(i)
                self.draft = rebuilt
            else:
                self.draft = None
            self.refresh(selected if selected in data.participants else None)
            self.tabs.setCurrentIndex(tab)
            for kind, text in searches.items():
                self.tables[kind][1].setText(text)
            self.set_project_dirty(True)
            self.update_collaboration_controls()
        finally:
            self.syncing_collaboration = False

    def sync_collaboration(self):
        if self.syncing_collaboration or self.collaboration.mode not in ("host", "client"):
            return True
        selected = self.selected_route
        self.syncing_collaboration = True
        enabled = self.centralWidget().isEnabled()
        self.centralWidget().setEnabled(False)
        try:
            self.collaboration.publish(self.data, self.project_settings())
        except ValueError as error:
            self.collaboration_error(str(error))
            return False
        finally:
            self.syncing_collaboration = False
            self.centralWidget().setEnabled(enabled)
            if self.collaboration.state is not None:
                self.receive_collaboration_state(self.collaboration.state)
                if selected in self.data.participants:
                    self.refresh(selected)
        return True

    def lock_nodes(self, nodes):
        if self.collaboration.mode not in ("host", "client"):
            return True
        enabled = self.centralWidget().isEnabled()
        self.centralWidget().setEnabled(False)
        try:
            self.collaboration.request("lock", {"nodes": list(set(nodes) - {None, ""})})
            return True
        except ValueError as error:
            self.collaboration_error(str(error))
            return False
        finally:
            self.centralWidget().setEnabled(enabled)

    def release_nodes(self):
        if self.collaboration.mode in ("host", "client"):
            try:
                self.collaboration.request("release")
            except ValueError:
                pass

    def set_project_dirty(self, dirty):
        self.dirty = dirty
        self.save_project_button.setObjectName("primary" if dirty else "")
        style = self.save_project_button.style()
        style.unpolish(self.save_project_button)
        style.polish(self.save_project_button)
        self.save_project_button.update()

    def warning_preferences_changed(self, *_):
        self.ignored_warnings = {
            warning for warning, toggle in self.warning_toggles.items() if toggle.isChecked()
        }
        self.set_project_dirty(True)
        self.sync_collaboration()
        if self.verify_on_change:
            self.verify_routes()
        else:
            self.verified = False
            self.route_diagnostics.clear()
            self.verification_signatures.clear()
            self.verification.setText(tr("Warning preferences changed. Verify routes again."))
            self.refresh()

    def set_respect_routes(self, enabled):
        self.respect_existing_routes = enabled
        self.project_settings_changed()

    def warning_multiplier_changed(self, warning, value):
        self.warning_multipliers[warning] = value / 1000
        self.warning_multiplier_labels[warning].setText(f"{value / 1000:.3f}×")
        self.project_settings_changed()

    def warning_minimization_changed(self, *_):
        self.minimize_warning_counts = {
            warning: toggle.isChecked()
            for warning, toggle in self.warning_minimization_toggles.items()
        }
        self.project_settings_changed()

    def project_settings(self):
        return ProjectSettings(
            safe_edit=self.safe_edit,
            minimum_segment_km=self.segment_preferences.minimum_km,
            maximum_segment_km=self.segment_preferences.maximum_km,
            ignored_warnings=self.ignored_warnings,
            warning_multipliers=self.warning_multipliers,
            minimize_warning_counts=self.minimize_warning_counts,
            respect_existing_routes=self.respect_existing_routes,
        )

    def save_project(self):
        if self.draft or self.address_worker is not None or self.solver_worker is not None:
            self.statusBar().showMessage(
                tr("Finish route editing or address lookup before saving the project.")
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save Project"),
            str(self.project_path or "dinner-safari.dsf"),
            tr("Dinner safari projects (*.dsf)"),
            "",
            QFileDialog.DontUseNativeDialog,
        )
        if not path:
            return
        if not path.lower().endswith(".dsf"):
            path += ".dsf"
        try:
            save_project(path, self.data, self.project_settings())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr("Save Project failed"), error_text(error))
            return
        self.project_path = Path(path)
        self.set_project_dirty(False)
        self.setWindowTitle(tr("{0} · Cykelfest", f"{self.project_path.name}"))
        self.statusBar().showMessage(tr("Saved project to {0}", f"{path}"))

    def new_project(self):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        if self.draft or self.address_worker is not None or self.solver_worker is not None:
            self.statusBar().showMessage(
                tr("Finish route editing or background work before creating a new project.")
            )
            return
        if (
            self.dirty
            and QMessageBox.question(
                self,
                tr("New Project"),
                tr("Create a new project and discard the current project's unsaved changes?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.apply_project(DinnerData(), ProjectSettings())
        self.tabs.setCurrentIndex(0)
        self.verification.setText(tr("Check course assignments and data references."))
        self.statusBar().showMessage(tr("New project created."))

    def load_project(self):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        if self.draft or self.address_worker is not None or self.solver_worker is not None:
            self.statusBar().showMessage(
                tr("Finish route editing or address lookup before loading a project.")
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Load Project"),
            str(self.project_path or ""),
            tr("Dinner safari projects (*.dsf)"),
            "",
            QFileDialog.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            data, settings = load_project(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr("Load Project failed"), error_text(error))
            return
        if (
            self.dirty
            and QMessageBox.question(
                self,
                tr("Replace unsaved project"),
                tr("Replace the current project and discard its unsaved changes?"),
            )
            != QMessageBox.Yes
        ):
            return
        self.apply_project(data, settings, Path(path))
        self.statusBar().showMessage(tr("Loaded project from {0}", f"{path}"))

    def apply_project(self, data, settings, path=None):
        """Replace project state while retaining system preferences."""
        if not self.syncing_collaboration and self.collaboration.mode == "host":
            self.collaboration.replace(data, settings)
        self.data = data
        self.project_path = path
        self.set_project_dirty(False)
        self.pending_pairing = None
        self.focus_selected_route = False
        for _, search in self.tables.values():
            search.clear()
        self.routes.blockSignals(True)
        self.routes.clear()
        self.routes.blockSignals(False)
        self.route_diagnostics.clear()
        self.verification_signatures.clear()
        self.verified = False
        self.exported.clear()
        controls = (
            self.safe_edit_toggle,
            self.minimum_segment,
            self.maximum_segment,
            *self.warning_toggles.values(),
            *self.warning_sliders.values(),
            *self.warning_minimization_toggles.values(),
            self.respect_routes_toggle,
        )
        for control in controls:
            control.blockSignals(True)
        try:
            self.safe_edit_toggle.setChecked(settings.safe_edit)
            self.respect_routes_toggle.setChecked(settings.respect_existing_routes)
            for warning, toggle in self.warning_toggles.items():
                toggle.setChecked(warning in settings.ignored_warnings)
                self.warning_minimization_toggles[warning].setChecked(
                    settings.minimize_warning_counts[warning]
                )
                self.warning_sliders[warning].setValue(
                    round(settings.warning_multipliers[warning] * 1000)
                )
                self.warning_sliders[warning].setEnabled(warning not in settings.ignored_warnings)
                self.warning_multiplier_labels[warning].setText(
                    f"{settings.warning_multipliers[warning]:.3f}×"
                )
            self.minimum_segment.setRange(0, 1000)
            self.maximum_segment.setRange(0, 1000)
            self.minimum_segment.setValue(settings.minimum_segment_km)
            self.maximum_segment.setValue(settings.maximum_segment_km)
            self.minimum_segment.setMaximum(settings.maximum_segment_km)
            self.maximum_segment.setMinimum(settings.minimum_segment_km)
        finally:
            for control in controls:
                control.blockSignals(False)
        self.safe_edit = settings.safe_edit
        self.ignored_warnings = set(settings.ignored_warnings)
        self.warning_multipliers = dict(settings.warning_multipliers)
        self.minimize_warning_counts = dict(settings.minimize_warning_counts)
        self.respect_existing_routes = settings.respect_existing_routes
        self.segment_preferences = SegmentPreferences(
            settings.minimum_segment_km, settings.maximum_segment_km
        )
        self.refresh()
        if self.verify_on_change:
            self.verify_routes()
        else:
            self.verification.setText(tr("Project loaded. Verify routes to check assignments."))
        self.setWindowTitle(
            tr("{0} · Cykelfest", self.project_path.name)
            if self.project_path
            else tr("Cykelfest · Dinner safari planner")
        )

    def segment_preferences_changed(self, *_):
        self.segment_preferences.minimum_km = self.minimum_segment.value()
        self.segment_preferences.maximum_km = self.maximum_segment.value()
        self.minimum_segment.setMaximum(self.maximum_segment.value())
        self.maximum_segment.setMinimum(self.minimum_segment.value())
        if self.verify_on_change:
            self.verify_affected_routes()
        else:
            self.verified = False
            self.route_diagnostics.clear()
            self.verification_signatures.clear()
            self.verification.setText(tr("Length preferences changed. Verify routes again."))
            self.refresh()

    def set_safe_edit(self, enabled):
        self.safe_edit = enabled
        if self.draft:
            self.draft.safe_edit = enabled
            self.selection_changed()

    def apply_theme(self, dark):
        self.dark_mode = dark
        colors = palette(dark)
        style = stylesheet(STYLE, dark)
        QApplication.instance().setPalette(colors)
        QApplication.instance().setStyleSheet(style)
        self.setPalette(colors)
        self.setStyleSheet(style)
        self.route_details.document().setDefaultStyleSheet(
            f"a {{ color: {'#68cfba' if dark else '#187f71'}; }}"
        )
        self.refresh()
        if self.enable_map:
            css = json.dumps(map_css(dark))
            self.map.page().runJavaScript(
                f"(() => {{ const theme = document.getElementById('cykelfest-theme'); if (theme) theme.textContent = {css}; }})();"
            )

    def set_verify_on_change(self, enabled):
        self.verify_on_change = enabled
        if enabled:
            self.verify_routes()
        elif self.draft:
            self.verified = False
            self.route_diagnostics.clear()
            self.verification_signatures.clear()
            self.verification.setText(
                tr("Automatic verification off. Verify after saving your edits.")
            )
            self.refresh()

    def build_map_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.map = QWebEngineView() if self.enable_map else QTextBrowser()
        self.map_bridge = MapBridge(self)
        if self.enable_map:
            self.map_channel = QWebChannel(self.map.page())
            self.map_channel.registerObject("routeEditor", self.map_bridge)
            self.map.page().setWebChannel(self.map_channel)
            self.map.loadFinished.connect(lambda success: self.set_map_style() if success else None)
        self.map.setMinimumHeight(300)
        left_layout.addWidget(self.map, 4)
        controls = QFrame()
        controls.setObjectName("card")
        control_layout = QVBoxLayout(controls)
        control_layout.addWidget(label(tr("Map display"), "section"))
        row = QVBoxLayout()
        self.map_mode = QComboBox()
        for mode in ("Selected route", "All routes", "Hosts only"):
            self.map_mode.addItem(tr(mode), mode)
        self.map_mode.currentTextChanged.connect(self.refresh_map)
        display_row = QHBoxLayout()
        display_row.addWidget(self.map_mode, 1)
        self.fit_hosts_button = button("", self.fit_hosts)
        self.fit_hosts_button.setFixedSize(36, 36)
        self.fit_hosts_button.setStyleSheet("padding:0;")
        self.fit_hosts_button.setToolTip(tr("Fit to hosts"))
        self.fit_hosts_button.setAccessibleName(tr("Fit to hosts"))
        self.fit_hosts_button.setIcon(course_icon("center", self.dark_mode))
        display_row.addWidget(self.fit_hosts_button)
        row.addLayout(display_row)
        self.show_hosts = QCheckBox(tr("Show host locations"))
        self.show_hosts.setChecked(True)
        self.show_hosts.toggled.connect(self.refresh_map)
        row.addWidget(self.show_hosts)
        control_layout.addLayout(row)
        control_layout.addWidget(label(tr("Map key"), "subtitle"))
        key = QGridLayout()
        key.setHorizontalSpacing(12)
        key.setVerticalSpacing(8)
        for index, (course, color) in enumerate(STOP_OUTLINES.items()):
            entry = QWidget()
            legend_row = QHBoxLayout(entry)
            legend_row.setContentsMargins(0, 0, 0, 0)
            circle = QFrame()
            circle.setFixedSize(16, 16)
            circle.setStyleSheet(
                f"border:3px solid {color};border-radius:8px;background:transparent;"
            )
            legend_row.addWidget(circle)
            legend_row.addWidget(label(tr(course)))
            legend_row.addStretch()
            key.addWidget(entry, index // 3, index % 3)
        control_layout.addLayout(key)
        bottom = QHBoxLayout()
        bottom.addWidget(controls, 1)
        self.solution_info = QTextBrowser()
        self.solution_info.setMinimumHeight(140)
        bottom.addWidget(self.solution_info, 1)
        left_layout.addLayout(bottom, 1)
        right = QWidget()
        right.setMinimumWidth(330)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        details = QVBoxLayout(card)
        details.addWidget(label(tr("Selected route"), "section"))
        self.route_title = label(tr("Select or add a route"))
        self.route_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        details.addWidget(self.route_title)
        self.course_controls = []
        for index, course in enumerate(COURSES):
            row = QHBoxLayout()
            text = label("")
            text.linkActivated.connect(lambda sid: self.jump_to("stops", sid))
            row.addWidget(text, 1)
            center = QToolButton()
            center.setIconSize(QSize(20, 20))
            center.setToolTip(tr("Center map on {0}", tr(course)))
            center.setAccessibleName(tr("Center {0}", tr(course)))
            center.clicked.connect(lambda checked=False, i=index: self.center_stop(i))
            row.addWidget(center)
            edit = QToolButton()
            edit.setIconSize(QSize(20, 20))
            edit.setToolTip(tr("Choose a stop for {0}", tr(course)))
            edit.setAccessibleName(tr("Edit {0}", tr(course)))
            menu = QMenu(edit)
            menu.aboutToShow.connect(lambda i=index, m=menu: self.populate_stop_menu(i, m))
            edit.setMenu(menu)
            edit.setPopupMode(QToolButton.InstantPopup)
            row.addWidget(edit)
            details.addLayout(row)
            self.course_controls.append((text, center, edit))
        self.route_details = QTextBrowser()
        self.route_details.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.route_details.setOpenLinks(False)
        self.route_details.anchorClicked.connect(lambda url: self.jump_to("stops", url.toString()))
        details.addWidget(self.route_details, 1)
        self.edit_help = label("", "subtitle")
        details.addWidget(self.edit_help)
        route_actions = QHBoxLayout()
        self.edit_route_button = button(tr("Edit on Map"), self.edit_route)
        self.revert_route_button = button(tr("Revert"), self.revert_route)
        self.save_route_button = button(tr("Save"), self.save_route, True)
        for action in (self.edit_route_button, self.revert_route_button, self.save_route_button):
            route_actions.addWidget(action)
        details.addLayout(route_actions)
        right_layout.addWidget(card, 5)
        right_layout.addWidget(label(tr("Routes"), "section"))
        route_row = QHBoxLayout()
        self.routes = QListWidget()
        self.routes.setSelectionMode(QAbstractItemView.SingleSelection)
        self.routes.currentItemChanged.connect(self.selection_changed)
        route_row.addWidget(self.routes, 1)
        actions = QVBoxLayout()
        self.add_route_button = button(tr("+ Add"), self.add_route)
        actions.addWidget(self.add_route_button)
        self.remove_route_button = button(tr("Remove"), self.remove_route)
        actions.addWidget(self.remove_route_button)
        self.clear_routes_button = button(tr("Clear Routes"), self.clear_routes)
        actions.addWidget(self.clear_routes_button)
        actions.addStretch()
        route_row.addLayout(actions)
        right_layout.addLayout(route_row, 3)
        self.verify_button = button(tr("Verify all routes"), self.verify_routes, True)
        right_layout.addWidget(self.verify_button)
        self.generate_routes_button = button(tr("Generate Routes"), self.generate_routes, True)
        self.generate_routes_button.setToolTip(
            tr(
                "Generate all three courses for every participant using straight-line distances. Review the result before applying it."
            )
        )
        generation_row = QHBoxLayout()
        self.pre_gen_button = button(tr("Pre-Gen"), lambda: self.generate_routes(pre_generate=True))
        self.pre_gen_button.setToolTip(
            tr(
                "Randomly seed disjoint routes for up to 25% of participants (rounded down). Each owner hosts appetizer and both segments meet the preferred limits. Existing assignments are kept. Enables Respect existing routes."
            )
        )
        generation_row.addWidget(self.pre_gen_button)
        generation_row.addWidget(self.generate_routes_button, 1)
        right_layout.addLayout(generation_row)
        self.verification = label(tr("Check course assignments and data references."), "subtitle")
        right_layout.addWidget(self.verification)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([880, 440])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        self.tabs.addTab(page, tr("Map"))

    def build_data_tab(self, kind):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(
            label(
                {
                    "participants": tr("Participants & pairings"),
                    "stops": tr("Dinner stops"),
                    "routes": tr("Dinner routes"),
                }[kind],
                "section",
            )
        )
        top.addStretch()
        search = QLineEdit()
        search.setPlaceholderText(tr("Search this table…"))
        search.setClearButtonEnabled(True)
        search.setMaximumWidth(320)
        search.textChanged.connect(lambda text: self.filter_table(kind, text))
        top.addWidget(search)
        layout.addLayout(top)
        body = QHBoxLayout()
        table = QTableWidget()
        headers = {
            "participants": [
                tr("ID"),
                tr("Name / pairing"),
                tr("Address"),
                tr("Route"),
                tr("Allergies"),
            ],
            "stops": [tr("ID"), tr("Host"), tr("Guests"), tr("Course")],
            "routes": [tr("ID"), *[tr(course) for course in COURSES]],
        }[kind]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        if kind == "stops":
            table.setItemDelegateForColumn(2, GuestCellDelegate(table))
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.AscendingOrder)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.cellDoubleClicked.connect(
            lambda row, col: (
                self.edit_record(kind)
                if (kind == "participants" and col != 3) or (kind != "participants" and col < 1)
                else self.table_clicked(kind, row, col)
            )
        )
        self.tables[kind] = (table, search)
        table.model().layoutChanged.connect(lambda *_: self.filter_table(kind, search.text()))
        body.addWidget(table, 1)
        actions = QVBoxLayout()
        if kind == "participants":
            self.host_only_controls = []
        import_button = button(tr("Import CSV"), lambda: self.import_csv(kind), True)
        self.host_only_controls.append(import_button)
        actions.addWidget(import_button)
        actions.addWidget(button(tr("Export CSV"), lambda: self.export_csv(kind)))
        if kind == "participants":
            self.find_addresses_button = button(tr("Find Addresses"), self.find_addresses)
            self.find_addresses_button.setToolTip(
                tr(
                    "Find coordinates for all participants without coordinates. Sends their addresses to Photon (OpenStreetMap data); existing coordinates are preserved. Include city and country for better results."
                )
            )
            actions.addWidget(self.find_addresses_button)
        actions.addSpacing(20)
        if kind != "routes":
            actions.addWidget(button(tr("Add"), lambda: self.edit_record(kind, new=True)))
        actions.addWidget(button(tr("Edit selected"), lambda: self.edit_record(kind)))
        actions.addWidget(button(tr("Remove selected"), lambda: self.remove_record(kind)))
        delete_all = button(tr("Delete all"), lambda: self.delete_all_records(kind))
        self.host_only_controls.append(delete_all)
        actions.addWidget(delete_all)
        if kind == "routes":
            actions.addWidget(button(tr("Show participant"), self.show_route_participant))
        actions.addStretch()
        body.addLayout(actions)
        layout.addLayout(body, 1)
        layout.addWidget(
            label(
                tr(
                    "Double-click a route ID to open its Routes row. Participants may have one route."
                )
                if kind == "participants"
                else (
                    tr(
                        "Double-click a host or guest ID to open its Participants row. Hover an ID to see the name. Use Edit selected to change a stop."
                    )
                    if kind == "stops"
                    else tr(
                        "Double-click a course stop ID to open its Stops row. Edit selected changes route assignments."
                    )
                ),
                "subtitle",
            )
        )
        self.tabs.addTab(page, tr("Data · {0}", tr(kind.title())))

    @property
    def selected_route(self):
        if self.draft:
            return self.draft.participant_id
        if self.pending_pairing:
            return self.pending_pairing
        item = self.routes.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh(self, selected=None):
        self.data.ensure_routes()
        selected = selected or self.selected_route
        self.routes.blockSignals(True)
        self.routes.clear()
        route_data = self.draft.data if self.draft else self.data
        for participant in route_data.participants.values():
            route = route_data.route_for(participant.id)
            if route is None:
                continue
            diagnostics = self.route_diagnostics.get(participant.id, {})
            errors = diagnostics.get("errors", [])
            warnings = diagnostics.get("warnings", [])
            prefix = tr("Conflict · ") if errors else (tr("Checked · ") if diagnostics else "")
            badges = (f"  ⛔ {len(errors)}" if errors else "") + (
                f"  ⚠ {len(warnings)}" if warnings else ""
            )
            course_count = sum(bool(sid) for sid in route.stops)
            item = QListWidgetItem(
                f"{participant.name}{badges}\n{prefix}{route.id} · {participant.id} · {course_count}/3 {tr('courses')}"
            )
            item.setData(Qt.UserRole, participant.id)
            if errors:
                item.setForeground(QColor("#ff9791" if self.dark_mode else "#b13d38"))
            item.setToolTip(
                "\n".join(
                    [
                        *(tr("Error: {0}", tr(issue)) for issue in errors),
                        *(tr("Warning: {0}", tr(issue)) for issue in warnings),
                    ]
                )
            )
            self.routes.addItem(item)
            entry = QWidget()
            entry.setMinimumHeight(66)
            entry.setAutoFillBackground(True)
            row_layout = QHBoxLayout(entry)
            row_layout.setContentsMargins(8, 8, 8, 8)
            text = label(
                f"{participant.name}\n{prefix}{route.id} · {participant.id} · {course_count}/3 {tr('courses')}"
            )
            row_layout.addWidget(text, 1)
            for severity, messages, icon_type in (
                ("warnings", warnings, QStyle.SP_MessageBoxWarning),
                ("errors", errors, QStyle.SP_MessageBoxCritical),
            ):
                if not messages:
                    continue
                icon = QLabel()
                icon.setObjectName(f"route_{severity}")
                icon.setPixmap(self.style().standardIcon(icon_type).pixmap(18, 18))
                icon.setToolTip("\n".join(translate_message(message) for message in messages))
                row_layout.addWidget(icon)
                count = label(str(len(messages)))
                count.setToolTip(icon.toolTip())
                row_layout.addWidget(count)
            item.setSizeHint(entry.sizeHint())
            self.routes.setItemWidget(item, entry)
            if participant.id == selected:
                self.routes.setCurrentItem(item)
        if not self.routes.currentItem() and self.routes.count():
            self.routes.setCurrentRow(0)
        self.routes.blockSignals(False)
        for kind, (table, search) in self.tables.items():
            selected_record = self.selected_record(kind)
            records = getattr(self.data, kind)
            table.setSortingEnabled(False)
            table.clearContents()
            table.setRowCount(len(records))
            for row, record in enumerate(records.values()):
                values = (
                    [record.id, record.name, record.address, record.route_id, record.allergies]
                    if kind == "participants"
                    else (
                        [record.id, record.host, ", ".join(record.guests), tr(record.course)]
                        if kind == "stops"
                        else [record.id, *record.stops]
                    )
                )
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, record.id)
                    if kind == "participants" and col == 0:
                        item.setToolTip(record.name)
                    elif kind == "stops" and col == 0:
                        host = self.data.participants.get(record.host)
                        item.setToolTip(host.name if host else tr("Host unavailable"))
                    elif kind == "routes" and col == 0:
                        participant = self.data.participant_for_route(record.id)
                        item.setToolTip(
                            participant.name if participant else tr("Participant unavailable")
                        )
                    if value and (
                        (kind == "participants" and col == 3)
                        or (kind == "stops" and col == 1)
                        or (kind == "routes" and col >= 1)
                    ):
                        item.setForeground(QColor("#68cfba" if self.dark_mode else "#187f71"))
                        font = QFont()
                        font.setUnderline(True)
                        item.setFont(font)
                        if kind == "stops":
                            person = self.data.participants.get(value)
                        elif kind == "routes":
                            stop = self.data.stops.get(value)
                            person = self.data.participants.get(stop.host) if stop else None
                        else:
                            person = record
                        item.setToolTip(person.name if person else tr("Reference unavailable"))
                    table.setItem(row, col, item)
                if kind == "stops" and record.guests:
                    links = ReferenceLinks(
                        ", ".join(
                            f'<a style="color:{"#68cfba" if self.dark_mode else "#187f71"}" href="{escape(pid, quote=True)}">{escape(pid)}</a>'
                            for pid in record.guests
                        )
                    )
                    links.setMargin(8)
                    links.setTextFormat(Qt.RichText)
                    links.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
                    links.referenceActivated.connect(lambda pid: self.jump_to("participants", pid))
                    links.linkHovered.connect(
                        lambda pid, widget=links: self.guest_hover(widget, pid)
                    )
                    table.setCellWidget(row, 2, links)
            table.setSortingEnabled(True)
            for row in range(table.rowCount()):
                if table.item(row, 0).data(Qt.UserRole) == selected_record:
                    table.selectRow(row)
            self.filter_table(kind, search.text())
        self.counts.setText(
            tr(
                "{0} pairings  ·  {1} stops  ·  {2} routes",
                f"{len(self.data.participants)}",
                f"{len(self.data.stops)}",
                f"{len(self.data.routes)}",
            )
        )
        self.selection_changed()
        self.statusBar().showMessage(
            tr("Ready · Save Project to keep all tables and project settings")
            + (tr(" · unsaved changes") if self.dirty else "")
        )

    def changed(self, selected=None):
        self.sync_collaboration()
        self.set_project_dirty(True)
        self.exported.clear()
        self.verification.setText(tr("Data changed. Verify routes again."))
        if self.verify_on_change:
            self.verify_affected_routes(selected)
        else:
            self.verified = False
            self.route_diagnostics.clear()
            self.verification_signatures.clear()
            self.refresh(selected)

    def selection_changed(self, *_):
        self.fit_hosts_button.setIcon(course_icon("center", self.dark_mode))
        self.update_solution_info()
        from html import escape

        # Qt updates the current item before the selection flags. Use the same
        # current item as the route details so the highlight cannot lag a click.
        current = self.routes.currentItem()
        for index in range(self.routes.count()):
            item = self.routes.item(index)
            widget = self.routes.itemWidget(item)
            if widget:
                widget.setBackgroundRole(QPalette.Highlight if item == current else QPalette.Base)
        if not self.draft:
            item = self.routes.currentItem()
            if self.pending_pairing and item and item.data(Qt.UserRole) != self.pending_pairing:
                pid = item.data(Qt.UserRole)
                self.pending_pairing = None
                self.refresh(pid)
                return
        pid = self.selected_route
        data = self.draft.data if self.draft else self.data
        for index, (text, center, edit) in enumerate(self.course_controls):
            center.setIcon(course_icon("center", self.dark_mode))
            edit.setIcon(course_icon("edit", self.dark_mode))
            stop = data.stops.get(data.route_stops(pid)[index]) if pid else None
            host = data.participants.get(stop.host) if stop else None
            sid = data.route_stops(pid)[index] if pid else ""
            ref = (
                f'<a href="{escape(sid, quote=True)}">{escape(sid)}</a>'
                if sid
                else tr("Unassigned")
            )
            text.setText(
                f"<b>{tr(COURSES[index])}</b><br>{ref} · {escape(host.name) if host else tr('Host unavailable')}"
            )
            center.setEnabled(bool(host and host.latitude is not None and self.enable_map))
            edit.setEnabled(pid is not None)
        self.edit_route_button.setEnabled(pid is not None and self.draft is None)
        self.remove_route_button.setEnabled(pid is not None and self.draft is None)
        self.revert_route_button.setEnabled(self.draft is not None)
        self.save_route_button.setEnabled(self.draft is not None)
        self.edit_help.setText("")
        if self.draft:
            next_course = self.draft.next_course
            next_text = (
                tr(COURSES[next_course]) if next_course is not None else tr("All courses assigned")
            )
            self.edit_help.setText(
                tr(
                    "Editing · {0}. Click to fill the next empty course, or drag between addresses. Blue: own address · green: 0 guests · lime: 1 · yellow: 2+. Save commits; Revert discards.",
                    f"{next_text}",
                )
            )
        if not pid:
            self.route_title.setText(tr("Select or add a route"))
            self.route_details.setHtml(
                translate_html("<p>Add participants and stops, then create a route.</p>")
            )
        else:
            participant = data.participants[pid]
            self.route_title.setText(participant.name + (tr(" · draft") if self.draft else ""))
            lines = []
            points = data.coordinates(pid)
            if all(point is not None for point in points):
                legs = [geodesic(a, b).km for a, b in pairwise(points)]
                lines.append(
                    f"<p><b>{sum(legs):.1f} km estimated</b><br>Legs: {' / '.join(f'{leg:.1f} km' for leg in legs)}<br>Straight-line distance</p>"
                )
            else:
                lines.append("<p>Set all host coordinates to preview the complete route.</p>")
            if self.verified and (self.draft is None or self.verify_on_change):
                diagnostics = self.route_diagnostics.get(pid, {})
                issues = [
                    *(tr("Error: {0}", tr(issue)) for issue in diagnostics.get("errors", [])),
                    *(tr("Warning: {0}", tr(issue)) for issue in diagnostics.get("warnings", [])),
                ]
                lines.append(
                    f"<p style='color:{'#ff9791' if self.dark_mode else '#b13d38'}'>"
                    + "<br>".join(escape(issue) for issue in issues)
                    + "</p>"
                    if issues
                    else "<p>✓ No route warnings or errors.</p>"
                )
            self.route_details.setHtml(translate_html("".join(lines)))
        if self.draft:
            self.map_bridge.publish(self.draft)
        else:
            self.refresh_map()

    def refresh_map(self, *_):
        if not hasattr(self, "routes"):
            return
        html = map_html(
            self.draft.data if self.draft else self.data,
            self.selected_route,
            self.map_mode.currentData(),
            self.show_hosts.isChecked(),
            self.draft,
            dark=self.dark_mode,
            map_style=self.map_style,
            focus_route=self.focus_selected_route,
            locked_hosts=self.collaboration.foreign_nodes(),
        )
        preserve_view = (
            self.collaboration.mode in ("host", "client") and not self.focus_selected_route
        )
        self.focus_selected_route = False
        if self.enable_map:
            self.map_reload_serial += 1
            serial = self.map_reload_serial

            def install(view=None):
                if serial != self.map_reload_serial:
                    return
                document = html
                if isinstance(view, dict) and "center" in view and "zoom" in view:
                    document = document.replace(
                        "</html>",
                        "<script>window.cykelfestMap.setView("
                        + json.dumps(view["center"])
                        + ","
                        + json.dumps(view["zoom"])
                        + ");</script></html>",
                    )
                self.map.setHtml(document, QUrl("https://cykelfest.local/"))

            if preserve_view:
                self.map.page().runJavaScript(
                    "(() => { const m=window.cykelfestMap; if (!m) return null; const c=m.getCenter(); return {center:[c.lat,c.lng],zoom:m.getZoom()}; })()",
                    install,
                )
            else:
                install()
        else:
            self.map.setHtml(translate_html("<p>Map disabled for offline UI verification.</p>"))

    def select_map_route(self, participant_id):
        if self.draft is not None or participant_id not in self.data.participants:
            return
        route = self.data.route_for(participant_id)
        if route is None or not route.has_route:
            return
        self.pending_pairing = None
        self.focus_selected_route = True
        self.refresh(participant_id)

    def fit_hosts(self):
        if self.enable_map:
            self.map.page().runJavaScript(
                "if (window.cykelfestFitHosts) window.cykelfestFitHosts();"
            )

    def center_stop(self, index):
        pid = self.selected_route
        if not pid or not self.enable_map:
            return
        data = self.draft.data if self.draft else self.data
        point = data.coordinates(pid)[index]
        if point is not None:
            self.map.page().runJavaScript(
                f"if (window.cykelfestMap) window.cykelfestMap.flyTo({json.dumps(point)}, Math.max(15, window.cykelfestMap.getZoom()), {{duration: 0.5}});"
            )

    def populate_stop_menu(self, index, menu):
        menu.clear()
        pid = self.selected_route
        if not pid:
            return
        draft = self.draft or RouteDraft(self.data, pid, safe_edit=self.safe_edit)
        for host, stop in draft.choices(index):
            if host.id in self.collaboration.foreign_nodes():
                continue
            title = f"{stop.id if stop else tr('New stop')} · {host.name} · {host.address}"
            action = menu.addAction(title)
            action.setData(host.id)
            action.triggered.connect(
                lambda checked=False, h=host.id: self.replace_route_stop(index, h)
            )
        if not menu.actions():
            menu.addAction(tr("No eligible stops")).setEnabled(False)
        menu.addSeparator()
        remove = menu.addAction(tr("Remove this stop"))
        remove.setEnabled(bool(draft.stops[index]))
        remove.triggered.connect(lambda: self.replace_route_stop(index, None))

    def replace_route_stop(self, index, host_id):
        if host_id and not self.lock_nodes([host_id]):
            return
        if not self.draft:
            self.edit_route()
        if not self.draft:
            return
        try:
            if host_id is None:
                self.draft.remove(index)
            else:
                self.draft.replace(index, host_id)
        except ValueError as error:
            self.statusBar().showMessage(error_text(error))
        if self.verify_on_change:
            self.verify_affected_routes()
        else:
            self.selection_changed()

    def filter_table(self, kind, text):
        table = self.tables[kind][0]
        for row in range(table.rowCount()):
            values = [
                table.item(row, col).text()
                for col in range(table.columnCount())
                if table.item(row, col)
            ]
            table.setRowHidden(row, text.casefold() not in " ".join(values).casefold())

    def guest_hover(self, widget, participant_id):
        participant = self.data.participants.get(participant_id)
        if participant_id:
            name = participant.name if participant else tr("Unknown participant")
            widget.setToolTip(name)
            QToolTip.showText(QCursor.pos(), name, widget)
        else:
            widget.setToolTip("")
            QToolTip.hideText()

    def find_addresses(self):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        if self.address_worker is not None or self.draft or self.solver_worker is not None:
            return
        missing = [p for p in self.data.participants.values() if p.latitude is None]
        addresses = [(p.id, p.address.strip()) for p in missing if p.address.strip()]
        self.address_blank_count = len(missing) - len(addresses)
        if not addresses:
            QMessageBox.information(
                self,
                tr("Find Addresses"),
                tr(
                    "No addresses to look up. {0} participants without coordinates have an empty address.",
                    f"{self.address_blank_count}",
                ),
            )
            return
        self.address_lookup_data = self.data
        self.address_lookup_records = {p.id: p for p in missing}
        cache_path = (
            Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation))
            / "cykelfest-routing"
            / "photon-addresses.json"
        )
        self.address_progress = QProgressDialog(
            tr("Looking up addresses…"), tr("Cancel"), 0, len(addresses), self
        )
        self.address_progress.setWindowTitle(tr("Find Addresses · Photon / OpenStreetMap"))
        self.address_progress.setWindowModality(Qt.NonModal)
        self.address_progress.setMinimumDuration(0)
        self.address_progress.setAutoClose(False)
        self.address_progress.setAutoReset(False)
        worker = AddressWorker(addresses, cache_path, self)
        self.address_worker = worker
        self.find_addresses_button.setEnabled(False)
        self.new_project_button.setEnabled(False)
        self.save_project_button.setEnabled(False)
        self.load_project_button.setEnabled(False)
        self.generate_routes_button.setEnabled(False)
        self.pre_gen_button.setEnabled(False)
        self.address_progress.canceled.connect(worker.cancel)
        worker.progress.connect(self.address_lookup_progress)
        worker.results_ready.connect(self.address_lookup_results)
        worker.finished.connect(self.address_lookup_finished)
        worker.start()
        self.collaboration.set_busy(True)

    def address_lookup_progress(self, completed, total, address):
        self.address_progress.setLabelText(
            tr("{0}/{1} addresses checked\n{2}", f"{completed}", f"{total}", f"{address}")
        )
        self.address_progress.setValue(completed)

    def address_lookup_results(self, report):
        updated = 0
        for pid, address, coordinates in report["results"]:
            participant = self.data.participants.get(pid)
            if (
                self.data is not self.address_lookup_data
                or not participant
                or participant is not self.address_lookup_records.get(pid)
                or participant.address.strip() != address
                or participant.latitude is not None
            ):
                continue  # Never overwrite edits or apply results to a replaced dataset.
            participant.latitude, participant.longitude = coordinates
            if self.draft:
                draft_participant = self.draft.data.participants.get(pid)
                if (
                    draft_participant
                    and draft_participant.address == participant.address
                    and draft_participant.latitude is None
                ):
                    draft_participant.latitude, draft_participant.longitude = coordinates
            updated += 1
        if updated:
            self.changed()
        self.address_progress.close()
        message = tr(
            "Added coordinates for {0} participants. {1} skipped because their address is empty.",
            f"{updated}",
            f"{self.address_blank_count}",
        )
        stale = len(report["results"]) - updated
        if stale:
            message += tr(
                "\n{0} results skipped because the participant data changed during lookup.",
                f"{stale}",
            )
        if report["cancelled"]:
            message += "\nLookup cancelled; completed results were kept."
        problems = report["problems"]
        if problems:
            message += tr("\n{0} lookup/cache issues.", f"{len(problems)}")
        if not self.closing_after_lookup:
            dialog = QMessageBox(
                QMessageBox.Information, tr("Find Addresses"), message, QMessageBox.Ok, self
            )
            if problems:
                dialog.setDetailedText("\n".join(problems))
            dialog.exec()

    def address_lookup_finished(self):
        self.collaboration.set_busy(False)
        worker = self.address_worker
        self.address_worker = None
        self.find_addresses_button.setEnabled(True)
        self.new_project_button.setEnabled(self.draft is None)
        self.save_project_button.setEnabled(self.draft is None)
        self.load_project_button.setEnabled(self.draft is None)
        self.generate_routes_button.setEnabled(self.draft is None)
        self.pre_gen_button.setEnabled(self.draft is None)
        if worker:
            worker.deleteLater()
        self.update_collaboration_controls()
        if self.closing_after_lookup:
            self.closing_after_lookup = False
            self.close()

    def selected_record(self, kind):
        table = self.tables[kind][0]
        item = table.item(table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def table_clicked(self, kind, row, col):
        table = self.tables[kind][0]
        if kind == "participants" and col == 3:
            self.jump_to("routes", table.item(row, col).text())
        elif kind == "routes" and col >= 1:
            self.jump_to("stops", table.item(row, col).text())
        elif kind == "stops" and col == 1:
            self.jump_to("participants", table.item(row, col).text())

    def jump_to(self, kind, record_id):
        if self.draft:
            self.statusBar().showMessage(tr("Save or Revert the route before opening data tables."))
            return
        if not record_id:
            return
        table, search = self.tables[kind]
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == record_id:
                search.clear()
                self.tabs.setCurrentIndex({"participants": 1, "stops": 2, "routes": 3}[kind])
                table.selectRow(row)
                table.scrollToItem(table.item(row, 0))
                table.setFocus()
                return
        QMessageBox.information(
            self,
            tr("Reference unavailable"),
            tr(
                "{0} does not exist in {1}. Import or add the referenced record.",
                f"{record_id}",
                tr(kind),
            ),
        )

    def edit_record(self, kind, new=False):
        rid = None if new else self.selected_record(kind)
        if not new and rid is None:
            return
        nodes = []
        if rid:
            if kind == "participants":
                nodes = [rid]
            elif kind == "stops":
                nodes = [self.data.stops[rid].host]
            else:
                owner = self.data.participant_for_route(rid)
                nodes = [
                    owner.id,
                    *[
                        self.data.stops[sid].host
                        for sid in self.data.routes[rid].stops
                        if sid in self.data.stops
                    ],
                ]
        if not self.lock_nodes(nodes):
            return
        dialog = RecordDialog(self.data, kind, getattr(self.data, kind).get(rid), self)
        if dialog.exec() == QDialog.Accepted:
            record = dialog.result_record
            extra = (
                [record.host]
                if kind == "stops"
                else [self.data.stops[sid].host for sid in record.stops if sid in self.data.stops]
                if kind == "routes"
                else []
            )
            if not self.lock_nodes(extra):
                self.release_nodes()
                return
            if kind == "routes":
                participant = self.data.participant_for_route(record.id)
                draft = RouteDraft(self.data, participant.id, safe_edit=self.safe_edit)
                try:
                    for index, sid in enumerate(record.stops):
                        if sid != draft.stops[index]:
                            draft.replace_stop(index, sid)
                    draft.commit(self.data)
                except ValueError as error:
                    QMessageBox.warning(self, tr("Route edit rejected"), error_text(error))
                    self.release_nodes()
                    return
            else:
                getattr(self.data, kind)[record.id] = record
            self.changed()
        self.release_nodes()

    def show_route_participant(self):
        participant = self.data.participant_for_route(self.selected_record("routes"))
        if participant:
            self.jump_to("participants", participant.id)

    def remove_record(self, kind):
        rid = self.selected_record(kind)
        if rid is None:
            return
        self.confirm_data_deletion(kind, [rid])

    def delete_all_records(self, kind):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        self.confirm_data_deletion(kind, list(getattr(self.data, kind)))

    def confirm_data_deletion(self, kind, record_ids):
        if self.draft or not record_ids:
            return
        trial = deepcopy(self.data)
        trial.delete_records(kind, record_ids)
        before = snapshot(self.data, self.project_settings())
        patch = difference(before, snapshot(trial, self.project_settings()))
        if not self.lock_nodes(resources(patch, before)):
            return
        affected = []
        for table_kind in MODELS:
            original = getattr(self.data, table_kind)
            updated = getattr(trial, table_kind)
            for rid, record in original.items():
                if rid not in updated:
                    affected.append(tr("{0} / {1}: delete entry", tr(table_kind.title()), f"{rid}"))
                elif record != updated[rid]:
                    for field, value in record.model_dump().items():
                        new_value = getattr(updated[rid], field)
                        if value != new_value:
                            affected.append(
                                f"{tr(table_kind.title())} / {rid} / {field_label(field)}: {value} → {new_value or tr('[empty]')}"
                            )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle(tr("Delete data and clear references"))
        noun = "entry" if len(record_ids) == 1 else "entries"
        dialog.setText(tr("Delete {0} {1} {2}?", f"{len(record_ids)}", tr(kind[:-1]), tr(noun)))
        dialog.setInformativeText(
            tr(
                "Affected references will be cleared. Deleting participants also deletes their routes. Stops used only by deleted routes will also be deleted. This cannot be undone. Open Show Details to review all affected entries and references."
            )
        )
        dialog.setDetailedText("\n".join(translate_message(message) for message in affected))
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        dialog.button(QMessageBox.Yes).setText(tr("Delete and clear references"))
        dialog.setDefaultButton(QMessageBox.Cancel)
        if dialog.exec() == QMessageBox.Yes:
            trial = deepcopy(self.data)
            trial.delete_records(kind, record_ids)
            self.data = trial
            self.pending_pairing = None
            self.changed()
        self.release_nodes()

    def add_route(self):
        if self.draft:
            return
        dialog = ParticipantPicker(self.data, self)
        if dialog.exec() == QDialog.Accepted:
            self.pending_pairing = dialog.participant_id
            self.data.create_route(self.pending_pairing)
            self.changed(self.pending_pairing)
            self.edit_route()

    def edit_route(self):
        if self.collaboration.mode == "client" and self.collaboration.busy:
            return
        if self.selected_route and self.draft is None:
            nodes = [
                self.selected_route,
                *[
                    self.data.stops[sid].host
                    for sid in self.data.route_stops(self.selected_route)
                    if sid in self.data.stops
                ],
            ]
            if not self.lock_nodes(nodes):
                return
            self.draft = RouteDraft(self.data, self.selected_route, safe_edit=self.safe_edit)
            self.set_editing(True)
            self.selection_changed()
            self.refresh_map()

    def set_editing(self, editing):
        self.new_project_button.setEnabled(not editing and self.address_worker is None)
        self.save_project_button.setEnabled(not editing and self.address_worker is None)
        self.load_project_button.setEnabled(not editing and self.address_worker is None)
        self.routes.setEnabled(not editing)
        self.add_route_button.setEnabled(not editing)
        self.clear_routes_button.setEnabled(not editing)
        self.verify_button.setEnabled(not editing)
        self.generate_routes_button.setEnabled(not editing and self.address_worker is None)
        self.pre_gen_button.setEnabled(not editing and self.address_worker is None)
        self.export_results_button.setEnabled(not editing)
        self.map_mode.setEnabled(not editing)
        self.show_hosts.setEnabled(not editing)
        for index in (1, 2, 3):
            self.tabs.setTabEnabled(index, not editing)
        self.update_collaboration_controls()

    def map_gesture(self, session, start_host, end_host=None):
        if not self.draft or self.draft.session != session:
            return  # Ignore queued clicks from a closed editor or a replaced map document.
        if not self.lock_nodes([start_host, end_host]):
            return
        try:
            if end_host is None:
                self.draft.click(start_host)
            else:
                self.draft.draw(start_host, end_host)
            self.statusBar().showMessage(
                tr("Route draft updated · Save to commit or Revert to discard")
            )
        except ValueError as error:
            self.statusBar().showMessage(error_text(error))
        if self.verify_on_change:
            self.verify_affected_routes()
        else:
            self.selection_changed()

    def revert_route(self):
        if self.draft is None:
            return
        pid = self.draft.participant_id
        self.draft = None
        self.release_nodes()
        self.set_editing(False)
        if self.verify_on_change:
            self.verify_affected_routes(pid)
        else:
            self.refresh(pid)

    def remove_map_stop(self, session, index):
        if not self.draft or self.draft.session != session:
            return
        try:
            self.draft.remove(index)
            self.statusBar().showMessage(
                tr("Stop removed from draft · Save to commit or Revert to discard")
            )
        except ValueError as error:
            self.statusBar().showMessage(error_text(error))
        if self.verify_on_change:
            self.verify_affected_routes()
        else:
            self.selection_changed()

    def save_route(self):
        if self.draft is None:
            return
        pid, changed = self.draft.participant_id, self.draft.changed
        if changed:
            self.draft.commit(self.data)
        self.draft = None
        self.pending_pairing = None
        self.set_editing(False)
        if changed:
            self.changed(pid)
        else:
            self.refresh(pid)
        self.release_nodes()

    def set_route_diagnostics(self, participant_id, *, warnings=(), errors=()):
        """Set supplemental diagnostics; counts and tooltips update together."""
        self.route_diagnostics[participant_id] = {
            "warnings": list(warnings),
            "errors": list(errors),
        }
        self.refresh()

    def remove_route(self):
        if self.draft:
            return
        pid = self.selected_route
        if pid and (route := self.data.route_for(pid)) is not None:
            self.confirm_data_deletion("routes", [route.id])

    def clear_routes(self):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        self.confirm_data_deletion("routes", list(self.data.routes))

    def verify_routes(self, selected=None):
        data = self.draft.data if self.draft else self.data
        self.update_verification(
            data, [pid for pid in data.participants if data.route_for(pid) is not None], selected
        )

    def generate_routes(self, *, pre_generate=False):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        if self.draft or self.address_worker is not None or self.solver_worker is not None:
            return
        missing = [
            pid
            for pid, p in self.data.participants.items()
            if p.latitude is None or p.longitude is None
        ]
        if not self.data.participants or missing:
            message = (
                tr("Add participants first.")
                if not self.data.participants
                else "Find Addresses or enter coordinates before generating routes:\n"
                + ", ".join(missing)
            )
            QMessageBox.information(self, tr("Generate Routes"), message)
            return
        self.solver_source = self.data
        self.solver_snapshot = self.data_snapshot()
        worker = SolverWorker(
            self.data,
            self.segment_preferences,
            self.ignored_warnings,
            self.solver_maximum_time,
            self,
            respect_existing_routes=self.respect_existing_routes,
            warning_multipliers=self.warning_multipliers,
            minimize_warning_counts=self.minimize_warning_counts,
            pre_generate=pre_generate,
        )
        self.solver_worker = worker
        self.solver_progress = QProgressDialog(
            tr("Preparing automatic routes…"), tr("Cancel"), 0, 0, self
        )
        self.solver_progress.setWindowTitle(
            tr("Pre-Gen") if pre_generate else tr("Generate Routes")
        )
        self.solver_progress.setWindowModality(Qt.NonModal)
        self.solver_progress.setMinimumDuration(0)
        self.solver_progress.setAutoClose(False)
        self.solver_progress.canceled.connect(worker.cancel)
        self.solver_phase = tr("Preparing automatic routes…")
        self.solver_elapsed = QElapsedTimer()
        self.solver_elapsed.start()
        self.solver_timer = QTimer(self)
        self.solver_timer.setInterval(250)
        self.solver_timer.timeout.connect(self.update_solver_timer)
        self.solver_timer.start()
        worker.progress.connect(self.update_solver_phase)
        self.update_solver_timer()
        worker.finished.connect(self.solver_finished)
        self.centralWidget().setEnabled(False)
        self.collaboration.set_busy(True)
        worker.start()

    def update_solver_phase(self, message):
        self.solver_phase = translate_message(message)
        self.update_solver_timer()

    def update_solver_timer(self):
        seconds = self.solver_elapsed.elapsed() // 1000
        self.solver_progress.setLabelText(
            tr(
                "{0}\nElapsed: {1}:{2} · Time limit: {3}s",
                f"{self.solver_phase}",
                f"{seconds // 60:02d}",
                f"{seconds % 60:02d}",
                f"{self.solver_maximum_time}",
            )
        )

    def data_snapshot(self):
        return json.dumps(
            {
                kind: [record.model_dump() for record in getattr(self.data, kind).values()]
                for kind in ("participants", "stops", "routes")
            },
            sort_keys=True,
        )

    def solver_finished(self):
        try:
            self.finish_collaborative_solver()
        finally:
            self.collaboration.set_busy(False)

    def finish_collaborative_solver(self):
        worker = self.solver_worker
        self.solver_worker = None
        self.solver_timer.stop()
        self.solver_timer.deleteLater()
        self.solver_progress.canceled.disconnect(worker.cancel)
        self.solver_progress.close()
        self.centralWidget().setEnabled(True)
        result = worker.result
        worker.deleteLater()
        if self.closing_after_solve:
            self.closing_after_solve = False
            self.close()
            return
        if worker.cancelled.is_set() or result is None or result.status == "CANCELLED":
            self.statusBar().showMessage(tr("Generation cancelled; project unchanged."))
            return
        if result.data is None:
            QMessageBox.information(self, tr("Generate Routes"), translate_message(result.message))
            return
        if self.data is not self.solver_source or self.data_snapshot() != self.solver_snapshot:
            QMessageBox.information(
                self,
                tr("Generate Routes"),
                tr("The project changed during generation. The result was discarded."),
            )
            return
        if worker.pre_generate:
            self.data = result.data
            self.pending_pairing = None
            self.respect_routes_toggle.setChecked(True)
            self.changed()
            self.verify_routes()
            self.statusBar().showMessage(
                translate_message(result.message) + tr(" Respect existing routes enabled.")
            )
            QMessageBox.information(self, tr("Pre-Gen"), translate_message(result.message))
            return
        preview = SolverPreview(
            result,
            worker.preferences,
            worker.ignored_warnings,
            self,
            respect_existing_routes=worker.respect_existing_routes,
        )
        if preview.exec() == QDialog.Accepted:
            self.data = result.data
            self.pending_pairing = None
            self.routes.blockSignals(True)
            self.routes.clear()
            self.routes.blockSignals(False)
            self.changed()
            self.verify_routes()
            self.statusBar().showMessage(
                tr("Generated routes applied. Save Project to retain them.")
            )
        else:
            self.statusBar().showMessage(tr("Generated routes discarded; project unchanged."))

    def verify_single_route(self, participant_id):
        data = self.draft.data if self.draft else self.data
        self.update_verification(data, [participant_id])

    def verify_affected_routes(self, selected=None):
        data = self.draft.data if self.draft else self.data
        affected = [
            pid
            for pid in data.participants
            if data.route_for(pid) is not None
            if self.verification_signatures.get(pid)
            != route_signature(data, pid, self.segment_preferences, self.ignored_warnings)
        ]
        self.update_verification(data, affected, selected)

    def update_verification(self, data, participant_ids, selected=None):
        active = {pid for pid in data.participants if data.route_for(pid) is not None}
        for pid in set(self.route_diagnostics) - active:
            self.route_diagnostics.pop(pid, None)
            self.verification_signatures.pop(pid, None)
        for pid in set(participant_ids) & active:
            self.route_diagnostics[pid] = verify_route(
                data, pid, self.segment_preferences, self.ignored_warnings
            )
            self.verification_signatures[pid] = route_signature(
                data, pid, self.segment_preferences, self.ignored_warnings
            )
        self.verified = True
        bad = sum(bool(d.get("errors")) for d in self.route_diagnostics.values())
        warnings = sum(bool(d.get("warnings")) for d in self.route_diagnostics.values())
        missing = sum(data.route_for(pid) is None for pid in data.participants)
        self.refresh(selected)
        self.verification.setText(
            tr(
                "{0} routes with errors · {1} routes with warnings · {2} pairings without routes. Distances are straight-line estimates.",
                f"{bad}",
                f"{warnings}",
                f"{missing}",
            )
        )

    def import_csv(self, kind):
        if self.collaboration.mode == "client" or self.collaboration.locks:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import {0}", tr(kind)),
            "",
            tr("CSV files (*.csv)"),
            "",
            QFileDialog.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            try:
                source = csv_source(path, self.csv_delimiter)
                _, review = infer_csv_mapping(source, kind)
            except ValueError:
                source, review = None, True
            if review:
                dialog = CSVMappingDialog(path, kind, self.csv_delimiter, self)
                if dialog.exec() != QDialog.Accepted:
                    return
                records = dialog.records
            else:
                records = parse_csv(source, kind)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, tr("Import failed"), error_text(error))
            return
        if (
            getattr(self.data, kind)
            and QMessageBox.question(
                self,
                tr("Replace table"),
                tr(
                    "Replace all {0} with {1} imported rows? The other tables are kept; verify references afterwards.",
                    tr(kind),
                    f"{len(records)}",
                ),
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.data.replace_table(kind, records)
        except ValueError as error:
            QMessageBox.warning(self, tr("Import failed"), error_text(error))
            return
        if self.pending_pairing not in self.data.participants:
            self.pending_pairing = None
        self.changed()

    def export_csv(self, kind):
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export {0}", tr(kind)),
            f"{kind}.csv",
            tr("CSV files (*.csv)"),
            "",
            QFileDialog.DontUseNativeDialog,
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".csv"
        try:
            write_csv(path, getattr(self.data, kind), kind, self.csv_delimiter)
            self.exported.add(kind)
            self.statusBar().showMessage(
                tr(
                    "Exported {0} to {1}. Export the other tables to retain all data.",
                    tr(kind),
                    f"{path}",
                )
            )
        except OSError as error:
            QMessageBox.warning(self, tr("Export failed"), error_text(error))

    def export_results(self):
        if self.collaboration.mode == "client":
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export results"),
            "results.csv",
            tr("CSV files (*.csv)"),
            "",
            QFileDialog.DontUseNativeDialog,
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".csv"
        try:
            write_results(path, self.data, self.csv_delimiter)
            self.statusBar().showMessage(tr("Exported participant results to {0}", f"{path}"))
        except OSError as error:
            QMessageBox.warning(self, tr("Export failed"), error_text(error))

    def update_solution_info(self):
        data = self.draft.data if self.draft else self.data
        summary = solution_summary(data, self.route_diagnostics)
        html = "<h3>Solution information</h3><table width='100%'>"
        for title, value in summary.items():
            if title in ("warnings", "errors"):
                continue
            text = f"{value:.2f} km" if value is not None else "—"
            html += f"<tr><td>{tr(title)}</td><td>{text}</td></tr>"
        html += "</table><p>Straight-line estimates. Totals include only complete routes with coordinates.</p>"
        if not self.verified:
            html += "<p>Run Verify all routes to update warnings and errors.</p>"
        else:
            html += "<table width='100%'>"
            for severity, icon in (
                ("errors", QStyle.SP_MessageBoxCritical),
                ("warnings", QStyle.SP_MessageBoxWarning),
            ):
                self.solution_info.document().addResource(
                    QTextDocument.ImageResource,
                    QUrl(f"issue:{severity}"),
                    self.style().standardIcon(icon).pixmap(16, 16).toImage(),
                )
                for message, count in summary[severity].items():
                    html += f'<tr><td><img src="issue:{severity}" width="16" height="16"> {escape(tr(message))}</td><td>{count}</td></tr>'
            html += "</table><p>Counts show affected routes per issue type.</p>"
            if not summary["errors"] and not summary["warnings"]:
                html += "<p>No warnings or errors.</p>"
        self.solution_info.setHtml(translate_html(html))

    def load_demo(self):
        if (self.data.participants or self.data.stops) and QMessageBox.question(
            self,
            tr("Load sample data"),
            tr("Replace current data with three fictional Stockholm pairings?"),
        ) != QMessageBox.Yes:
            return
        self.data = demo_data()
        self.project_path = None
        self.setWindowTitle(tr("Cykelfest · Dinner safari planner"))
        self.pending_pairing = None
        self.changed()
        self.statusBar().showMessage(
            tr("Sample data · fictional pairings and illustrative coordinates")
        )

    def closeEvent(self, event):
        if self.solver_worker is not None:
            self.closing_after_solve = True
            self.solver_worker.cancel()
            self.statusBar().showMessage(tr("Cancelling route generation before closing…"))
            event.ignore()
            return
        if self.address_worker is not None:
            self.closing_after_lookup = True
            self.address_worker.cancel()
            self.statusBar().showMessage(tr("Cancelling address lookup before closing…"))
            event.ignore()
            return
        if (
            self.draft
            and self.draft.changed
            and QMessageBox.question(
                self,
                tr("Discard route draft?"),
                tr("Close and discard the unsaved map edits?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            event.ignore()
            return
        if (
            self.dirty
            and QMessageBox.question(
                self,
                tr("Close workspace"),
                tr(
                    "Your project has unsaved changes. Save Project before closing to retain all tables and project settings. Close anyway?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            event.ignore()
        else:
            self.collaboration.disconnect()
            event.accept()


def main():
    parser = argparse.ArgumentParser(description=tr("Cykelfest dinner safari planner"))
    parser.add_argument("--demo", action="store_true", help=tr("Start with fictional example data"))
    args = parser.parse_args()
    set_windows_app_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(tr("Cykelfest"))
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    window = MainWindow(demo_data() if args.demo else None)
    window.showMaximized()
    sys.exit(app.exec())
