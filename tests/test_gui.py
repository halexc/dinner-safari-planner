import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QDialog

from cykelfest_routing.data import Participant, demo_data
from cykelfest_routing.gui import (
    CSVMappingDialog,
    MainWindow,
    ParticipantPicker,
    RecordDialog,
    SolverPreview,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    window = MainWindow(
        demo_data(),
        enable_map=False,
        preferences=QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat),
    )
    yield window
    window.draft = None
    window.dirty = False
    window.close()


def test_tabs_reference_navigation_and_search(window):
    assert window.tabs.count() == 5
    table, search = window.tables["stops"]
    search.setText("missing")
    assert table.isRowHidden(0)
    window.table_clicked("participants", 0, 4)
    assert window.tabs.currentIndex() == 3
    window.table_clicked("routes", window.tables["routes"][0].currentRow(), 3)
    assert window.tabs.currentIndex() == 2
    assert search.text() == ""
    assert table.item(table.currentRow(), 1).text() == "S002"
    window.table_clicked("stops", 1, 2)
    assert window.tabs.currentIndex() == 1
    assert window.selected_record("participants") == "P002"


def test_new_project_resets_project_but_preserves_system_preferences(window, monkeypatch):
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from cykelfest_routing.project import ProjectSettings

    window.dark_mode_toggle.setChecked(True)
    window.delimiter_combo.setCurrentIndex(window.delimiter_combo.findData(";"))
    window.solver_time_control.setValue(75)
    window.safe_edit_toggle.setChecked(False)
    window.minimum_segment.setValue(1)
    window.respect_routes_toggle.setChecked(True)
    window.warning_toggles["Repeat meetups."].setChecked(True)
    window.warning_sliders["Repeat meetups."].setValue(2500)
    window.project_path = Path("previous.dsf")
    window.tables["participants"][1].setText("missing")
    window.verify_routes()
    assert window.dirty
    original = window.data
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    window.new_project_button.click()
    assert window.data is original and window.dirty
    assert window.project_path == Path("previous.dsf")

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.new_project_button.click()
    assert not window.data.participants and not window.data.stops and not window.data.routes
    assert window.project_path is None and not window.dirty
    assert window.project_settings() == ProjectSettings()
    assert not window.route_diagnostics and not window.verification_signatures
    assert window.routes.count() == 0 and window.selected_route is None
    assert all(
        table.rowCount() == 0 and not search.text() for table, search in window.tables.values()
    )
    assert window.dark_mode and window.csv_delimiter == ";" and window.solver_maximum_time == 75
    assert window.tabs.currentIndex() == 0
    assert window.save_project_button.objectName() == window.load_project_button.objectName()
    assert window.windowTitle() == "Bike Party · Dinner safari planner"


def test_save_project_style_tracks_unsaved_data_and_settings(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    assert window.save_project_button.objectName() == ""
    window.dark_mode_toggle.setChecked(True)
    assert not window.dirty and window.save_project_button.objectName() == ""
    window.minimum_segment.setValue(0.75)
    assert window.dirty and window.save_project_button.objectName() == "primary"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    window.save_project()
    assert window.dirty and window.save_project_button.objectName() == "primary"
    path = tmp_path / "saved.dsf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    window.save_project()
    assert not window.dirty and window.save_project_button.objectName() == ""
    window.changed()
    assert window.save_project_button.objectName() == "primary"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.load_project()
    assert not window.dirty and window.save_project_button.objectName() == ""


def test_new_project_cannot_replace_active_draft(window):
    from cykelfest_routing.route_edit import RouteDraft

    original = window.data
    window.draft = RouteDraft(window.data, "P001")
    window.set_editing(True)
    assert not window.new_project_button.isEnabled()
    window.new_project()
    assert window.data is original and window.draft is not None


def test_verification_highlights_conflicts_and_edit_invalidates_checks(window):
    window.data.route_for("P001").dessert_stop_id = "missing"
    window.verify_routes()
    item = window.routes.item(0)
    assert item.data(Qt.UserRole) == "P001"
    assert "Conflict" in item.text()
    assert "Route contains stop(s) without a host." in item.toolTip()
    window.changed()
    assert not window.verified
    assert "Verify routes again" in window.verification.text()


def test_record_dialog_rejects_duplicate_id_and_accepts_coordinates(window):
    dialog = RecordDialog(window.data, "participants", parent=window)
    assert dialog.fields["id"].text() == "P-00001"
    assert dialog.fields["id"].isReadOnly()
    dialog.fields["id"].setText("P001")
    dialog.fields["name"].setText("New pairing")
    dialog.save()
    assert "already exists" in dialog.error.text()
    dialog.fields["id"].setText("001")
    dialog.fields["latitude"].setText("59.3")
    dialog.fields["longitude"].setText("18.0")
    dialog.save()
    assert dialog.result() == QDialog.Accepted
    assert dialog.result_record.latitude == 59.3


def test_new_stops_get_generated_ids(window):
    dialog = RecordDialog(window.data, "stops", parent=window)
    assert dialog.fields["id"].text() == "S-00001"
    dialog.save()
    assert dialog.result_record.id == "S-00001"


def test_csv_mapping_dialog_selects_columns_and_delimiter(window, tmp_path):
    path = tmp_path / "external.csv"
    path.write_text('"People";"Place"\n"First";"Street, City"\n', encoding="utf-8")
    dialog = CSVMappingDialog(path, "participants", ",", window)
    dialog.delimiter_combo.setCurrentIndex(dialog.delimiter_combo.findData(";"))
    assert set(dialog.column_combos) >= {
        "id",
        "name",
        "address",
        "latitude",
        "longitude",
        "route_id",
    }
    dialog.column_combos["name"].setCurrentIndex(dialog.column_combos["name"].findData(0))
    dialog.column_combos["address"].setCurrentIndex(dialog.column_combos["address"].findData(1))
    dialog.confirm_mapping()
    assert dialog.result() == QDialog.Accepted
    assert dialog.records["P-00001"].address == "Street, City"


def test_ambiguous_csv_import_uses_mapping_and_cancel_preserves_data(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    path = tmp_path / "external.csv"
    path.write_text("People,Place\nFirst,Street\n")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    original = window.data
    monkeypatch.setattr(CSVMappingDialog, "exec", lambda dialog: QDialog.Rejected)
    window.import_csv("participants")
    assert window.data is original and len(window.data.participants) == 3

    def map_columns(dialog):
        for field, column in (("name", 0), ("address", 1)):
            dialog.column_combos[field].setCurrentIndex(
                dialog.column_combos[field].findData(column)
            )
        dialog.confirm_mapping()
        return dialog.result()

    monkeypatch.setattr(CSVMappingDialog, "exec", map_columns)
    window.import_csv("participants")
    assert list(window.data.participants) == ["P-00001"]
    assert window.data.participants["P-00001"].name == "First"


def test_wrong_delimiter_with_quoted_fields_opens_mapping_dialog(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    path = tmp_path / "data.csv"
    path.write_text('"name";"address"\n"First";"Street, City"\n')
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    opened = []

    def confirm(dialog):
        opened.append(True)
        assert dialog.delimiter_combo.currentData() == ";"
        dialog.confirm_mapping()
        return dialog.result()

    monkeypatch.setattr(CSVMappingDialog, "exec", confirm)
    window.import_csv("participants")
    assert opened and window.data.participants["P-00001"].address == "Street, City"
    assert window.csv_delimiter == ","


def test_system_preferences_survive_restart_without_dirtying_project(window):
    window.dark_mode_toggle.setChecked(True)
    window.verify_change_toggle.setChecked(True)
    window.delimiter_combo.setCurrentIndex(window.delimiter_combo.findData(";"))
    window.osm_combo.setCurrentIndex(window.osm_combo.findData("dark_matter"))
    window.solver_time_control.setValue(120)
    assert not window.dirty
    restarted = MainWindow(
        demo_data(),
        enable_map=False,
        preferences=QSettings(window.preferences.fileName(), QSettings.IniFormat),
    )
    try:
        assert restarted.dark_mode and restarted.verify_on_change and restarted.verified
        assert restarted.csv_delimiter == ";" and restarted.map_style == "dark_matter"
        assert restarted.osm_combo.currentData() == "dark_matter"
        assert restarted.solver_maximum_time == restarted.solver_time_control.value() == 120
        assert not restarted.dirty
        restarted.safe_edit_toggle.setChecked(False)
        assert restarted.dirty
        assert "safe_edit" not in restarted.preferences.allKeys()
    finally:
        restarted.dirty = False
        restarted.close()


def finish_generation(window, app):
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtTest import QTest

    timer = QElapsedTimer()
    timer.start()
    while window.solver_worker is not None and timer.elapsed() < 10000:
        app.processEvents()
        QTest.qWait(10)
    assert window.solver_worker is None
    assert window.centralWidget().isEnabled()


def test_generated_routes_are_previewed_then_applied(window, monkeypatch, app):
    from PySide6.QtWidgets import QTableWidget

    window.data.clear_routes()
    window.refresh()
    window.solver_time_control.setValue(3)
    previews = []

    def accept(dialog):
        table = dialog.findChild(QTableWidget)
        assert table.rowCount() == 3 and table.columnCount() == 6
        assert not window.data.routes  # Preview has not committed the candidate.
        previews.append(dialog)
        return QDialog.Accepted

    monkeypatch.setattr(SolverPreview, "exec", accept)
    window.generate_routes_button.click()
    assert not window.centralWidget().isEnabled()
    finish_generation(window, app)
    assert previews and len(window.data.routes) == 3
    assert window.dirty and window.verified
    assert all(not d["errors"] for d in window.route_diagnostics.values())


def test_respect_routes_generation_applies_completed_partial_route(window, monkeypatch, app):
    from cykelfest_routing.solver import validate_assignment
    from cykelfest_routing.verification import SegmentPreferences

    window.data.assign_route("P001", ["S001", "", "S003"])
    route_id = window.data.route_for("P001").id
    window.respect_routes_toggle.setChecked(True)
    window.solver_time_control.setValue(3)
    monkeypatch.setattr(SolverPreview, "exec", lambda dialog: QDialog.Accepted)
    window.generate_routes()
    finish_generation(window, app)
    assert window.data.route_stops("P001") == ["S001", "S002", "S003"]
    assert window.data.route_for("P001").id == route_id
    validate_assignment(window.data, SegmentPreferences())
    assert window.verified


def test_generation_timer_updates_and_stops_after_finish(window, monkeypatch, app):
    from types import SimpleNamespace

    monkeypatch.setattr(SolverPreview, "exec", lambda dialog: QDialog.Rejected)
    window.generate_routes()
    timer = window.solver_timer
    assert timer.isActive() and "Elapsed: 00:00" in window.solver_progress.labelText()
    window.update_solver_phase("Testing search phase")
    window.solver_elapsed = SimpleNamespace(elapsed=lambda: 65000)
    window.update_solver_timer()
    assert "Testing search phase" in window.solver_progress.labelText()
    assert "Elapsed: 01:05" in window.solver_progress.labelText()
    stopped = []
    close = window.solver_progress.close

    def close_progress():
        stopped.append(not timer.isActive())
        close()

    monkeypatch.setattr(window.solver_progress, "close", close_progress)
    finish_generation(window, app)
    assert stopped == [True] and window.solver_worker is None


def test_internal_pre_generation_preserves_seed_behavior(window, monkeypatch, app):
    from PySide6.QtWidgets import QMessageBox
    from test_solver import seed_data

    window.data = seed_data()
    window.minimum_segment.setValue(0.3)
    window.maximum_segment.setValue(2)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    assert not hasattr(window, "pre_gen_button")
    window.generate_routes(pre_generate=True)
    finish_generation(window, app)
    assert window.respect_existing_routes and window.respect_routes_toggle.isChecked()
    complete = [route for route in window.data.routes.values() if all(route.stops)]
    assert len(complete) == 2 and messages and "2/2" in messages[-1]
    assert all(not diagnostics["errors"] for diagnostics in window.route_diagnostics.values())
    assert window.dirty and window.verified


def test_discarded_or_cancelled_generation_preserves_project(window, monkeypatch, app):
    original = window.data
    monkeypatch.setattr(SolverPreview, "exec", lambda dialog: QDialog.Rejected)
    window.generate_routes()
    finish_generation(window, app)
    assert window.data is original and not window.dirty
    window.generate_routes()
    window.solver_worker.cancel()
    finish_generation(window, app)
    assert window.data is original and not window.dirty


def test_solver_preflight_and_stale_results_do_not_replace_project(window, monkeypatch, app):
    from PySide6.QtWidgets import QMessageBox

    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    window.data.participants["P001"].latitude = None
    window.data.participants["P001"].longitude = None
    window.generate_routes()
    assert window.solver_worker is None and "P001" in messages[-1]
    window.data = demo_data()
    window.generate_routes()
    window.data.participants["P001"].name = "Changed during generation"
    finish_generation(window, app)
    assert "changed during generation" in messages[-1]
    assert window.data.participants["P001"].name == "Changed during generation"


def test_closing_waits_for_solver_cancellation(window, app):
    window.generate_routes()
    window.close()
    assert window.closing_after_solve and window.solver_worker.cancelled.is_set()
    finish_generation(window, app)
    assert not window.closing_after_solve and not window.dirty


def test_warning_sliders_support_fractional_penalties_and_double_click_reset(window, app):
    from PySide6.QtTest import QTest

    window.tabs.setCurrentIndex(4)
    window.show()
    app.processEvents()
    slider = window.warning_sliders["Repeat meetups."]
    assert slider.minimum() == 0 and slider.maximum() == 5000
    slider.setValue(2345)
    assert window.warning_multipliers["Repeat meetups."] == 2.345
    assert window.warning_multiplier_labels["Repeat meetups."].text() == "2.345×"
    assert window.dirty
    QTest.mouseDClick(slider, Qt.LeftButton)
    assert slider.value() == 1000 and window.warning_multipliers["Repeat meetups."] == 1
    window.warning_toggles["Repeat meetups."].setChecked(True)
    assert not slider.isEnabled()
    window.warning_toggles["Repeat meetups."].setChecked(False)
    slider.setValue(0)
    window.verify_routes()
    assert "Repeat meetups." in window.route_diagnostics["P001"]["warnings"]


def test_route_lock_and_warning_sliders_are_project_preferences(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    path = tmp_path / "solver-settings.dsf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.respect_routes_toggle.setChecked(True)
    window.warning_sliders["Repeat meetups."].setValue(4567)
    assert all(toggle.isChecked() for toggle in window.warning_minimization_toggles.values())
    window.warning_minimization_toggles["Repeat meetups."].setChecked(False)
    assert window.warning_multipliers["Repeat meetups."] == 4.567
    window.verify_routes()
    assert "Repeat meetups." in window.route_diagnostics["P001"]["warnings"]
    window.save_project()
    window.warning_minimization_toggles["Repeat meetups."].setChecked(True)
    window.respect_existing_routes = False
    window.warning_multipliers["Repeat meetups."] = 0
    window.respect_routes_toggle.blockSignals(True)
    window.respect_routes_toggle.setChecked(False)
    window.respect_routes_toggle.blockSignals(False)
    window.load_project()
    assert window.respect_existing_routes and window.respect_routes_toggle.isChecked()
    assert window.warning_sliders["Repeat meetups."].value() == 4567
    assert window.warning_multipliers["Repeat meetups."] == 4.567
    assert not window.minimize_warning_counts["Repeat meetups."]
    assert not window.warning_minimization_toggles["Repeat meetups."].isChecked()
    assert not window.dirty


def test_solver_worker_receives_route_lock_and_penalty_preferences(window, monkeypatch, app):
    window.respect_routes_toggle.setChecked(True)
    window.warning_sliders["Repeat meetups."].setValue(2222)
    window.warning_minimization_toggles["Repeat meetups."].setChecked(False)
    original = {rid: route.model_copy(deep=True) for rid, route in window.data.routes.items()}
    monkeypatch.setattr(SolverPreview, "exec", lambda dialog: QDialog.Accepted)
    window.generate_routes()
    assert window.solver_worker.respect_existing_routes
    assert window.solver_worker.warning_multipliers["Repeat meetups."] == 2.222
    assert not window.solver_worker.minimize_warning_counts["Repeat meetups."]
    finish_generation(window, app)
    assert window.data.routes == original


def test_map_style_html_is_independent_of_gui_theme(window):
    from cykelfest_routing.map_view import MAP_STYLES, map_html

    for style, (_, tiles, _) in MAP_STYLES.items():
        html = map_html(window.data, "P001", "Selected route", True, dark=True, map_style=style)
        assert tiles in html
        assert "window.cykelfestBaseLayer" in html
        assert "invert(1)" not in html


def test_map_bridge_selects_route_and_requests_route_fit(window, monkeypatch):
    from cykelfest_routing import gui

    requests = []
    original = gui.map_html

    def capture(*args, **kwargs):
        requests.append((args[1], kwargs["focus_route"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(gui, "map_html", capture)
    window.map_bridge.selectRoute("P003")
    assert window.selected_route == "P003"
    assert requests[-1] == ("P003", True)
    window.edit_route()
    window.map_bridge.selectRoute("P002")
    assert window.selected_route == "P003" and window.draft.participant_id == "P003"


def test_save_load_project_restores_tables_settings_and_clean_state(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    path = tmp_path / "event"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path) + ".dsf", ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.dark_mode_toggle.setChecked(True)
    window.safe_edit_toggle.setChecked(False)
    window.verify_change_toggle.setChecked(True)
    window.minimum_segment.setValue(0.75)
    window.maximum_segment.setValue(5)
    window.delimiter_combo.setCurrentIndex(window.delimiter_combo.findData(";"))
    assert window.dirty
    window.save_project_button.click()
    assert (tmp_path / "event.dsf").exists()
    assert not window.dirty
    assert set(json.loads((tmp_path / "event.dsf").read_text())["settings"]) == {
        "safe_edit",
        "minimum_segment_km",
        "maximum_segment_km",
        "ignored_warnings",
        "respect_existing_routes",
        "warning_multipliers",
        "minimize_warning_counts",
    }
    window.data.assign_route("P001", ["", "", ""])
    window.dark_mode_toggle.setChecked(False)
    window.delimiter_combo.setCurrentIndex(window.delimiter_combo.findData("|"))
    window.osm_combo.setCurrentIndex(window.osm_combo.findData("dark_matter"))
    window.maximum_segment.setValue(2)
    window.load_project_button.click()
    assert window.data.route_for("P001").stops == ["S001", "S002", "S003"]
    assert not window.dark_mode and not window.safe_edit and window.verify_on_change
    assert window.csv_delimiter == "|" and window.map_style == "dark_matter"
    assert window.minimum_segment.value() == 0.75 and window.maximum_segment.value() == 5
    assert window.verified and not window.dirty
    assert "event.dsf" in window.windowTitle()


def test_invalid_load_preserves_current_project(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    path = tmp_path / "invalid.dsf"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[2]))
    original = window.data
    window.load_project()
    assert window.data is original and errors


def test_load_project_can_restore_larger_bounds_and_cancel_unsaved_replacement(
    window, monkeypatch, tmp_path
):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from cykelfest_routing.project import ProjectSettings, save_project

    path = tmp_path / "event.dsf"
    save_project(path, window.data, ProjectSettings(minimum_segment_km=6, maximum_segment_km=12))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    window.dirty = True
    original = window.data
    window.load_project()
    assert window.data is original and window.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.load_project()
    assert window.minimum_segment.value() == 6 and window.maximum_segment.value() == 12
    assert not window.dirty


def test_routes_tab_edit_updates_map_assignments_guests_and_verification(window, monkeypatch):
    window.verify_change_toggle.setChecked(True)
    table, _ = window.tables["routes"]
    assert [table.horizontalHeaderItem(i).text() for i in range(5)] == [
        "",
        "ID",
        "Appetizer",
        "Main dish",
        "Dessert",
    ]
    assert window.tables["participants"][0].columnCount() == 6
    table.selectRow(0)
    route_id = table.item(0, 1).text()

    def edit(dialog):
        assert dialog.kind == "routes"
        assert dialog.fields["id"].text() == route_id
        dialog.fields["main_stop_id"].setCurrentIndex(0)
        dialog.save()
        return dialog.result()

    monkeypatch.setattr(RecordDialog, "exec", edit)
    window.edit_record("routes")
    assert window.data.route_for("P001").stops == ["S001", "", "S003"]
    assert "P001" not in window.data.stops["S002"].guests
    assert (
        "Participant is not assigned all 3 stops." in window.route_diagnostics["P001"]["warnings"]
    )
    assert "Unassigned" in window.course_controls[1][0].text()
    assert window.tables["routes"][0].item(0, 3).text() == ""
    window.show_route_participant()
    assert window.selected_record("participants") == "P001"


def test_map_save_and_revert_update_separate_route_table(window):
    rid = window.data.participants["P001"].route_id
    window.edit_route()
    window.remove_map_stop(window.draft.session, 1)
    assert window.data.routes[rid].main_stop_id == "S002"
    window.revert_route()
    assert window.data.routes[rid].main_stop_id == "S002"
    window.edit_route()
    window.remove_map_stop(window.draft.session, 1)
    window.save_route()
    assert window.data.routes[rid].main_stop_id == ""
    assert window.tables["routes"][0].item(0, 3).text() == ""
    assert window.data.participants["P001"].route_id == rid


def test_table_sorting_preserves_selection_search_and_reference_navigation(window):
    table, search = window.tables["participants"]
    table.selectRow(0)
    table.sortItems(2, Qt.DescendingOrder)
    assert [table.item(row, 2).text() for row in range(3)] == sorted(
        [p.name for p in window.data.participants.values()], reverse=True
    )
    selected = window.selected_record("participants")
    window.refresh()
    assert window.selected_record("participants") == selected
    assert table.item(0, 2).text() == "Robin & Kim"
    search.setText("Charlie")
    table.sortItems(1, Qt.AscendingOrder)
    for row in range(table.rowCount()):
        assert table.isRowHidden(row) == (table.item(row, 1).text() != "P003")
    search.clear()
    table.sortItems(1, Qt.DescendingOrder)
    window.table_clicked("participants", 0, 4)
    assert window.tabs.currentIndex() == 3
    window.table_clicked("routes", window.tables["routes"][0].currentRow(), 3)
    assert window.selected_record("stops") == "S002"


def test_guest_links_names_and_navigation_survive_sorting(window, monkeypatch):
    from PySide6.QtWidgets import QToolTip

    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda point, name, widget: shown.append(name))
    table, _ = window.tables["stops"]
    table.sortItems(1, Qt.DescendingOrder)
    guests = table.cellWidget(0, 3)
    assert 'href="P001"' in guests.text()
    guests.linkHovered.emit("P001")
    assert shown == ["Alex & Sam"]
    guests.linkActivated.emit("P001")
    assert window.tabs.currentIndex() != 1
    from PySide6.QtTest import QTest

    QTest.mouseDClick(guests, Qt.LeftButton)
    assert window.tabs.currentIndex() == 1
    assert window.selected_record("participants") == "P001"


@pytest.mark.parametrize(
    "kind,column,target_tab", [("participants", 4, 3), ("stops", 2, 1), ("routes", 2, 2)]
)
def test_reference_cells_require_double_click(window, kind, column, target_tab):
    table = window.tables[kind][0]
    start_tab = {"participants": 1, "stops": 2, "routes": 3}[kind]
    window.tabs.setCurrentIndex(start_tab)
    table.cellClicked.emit(0, column)
    assert window.tabs.currentIndex() == start_tab
    table.cellDoubleClicked.emit(0, column)
    assert window.tabs.currentIndex() == target_tab


@pytest.mark.parametrize("kind", ["participants", "stops", "routes"])
def test_deletion_preview_can_cancel_or_clear_references(window, monkeypatch, kind):
    from copy import deepcopy

    from PySide6.QtWidgets import QMessageBox

    table = window.tables[kind][0]
    table.selectRow(0)
    rid = window.selected_record(kind)
    window.checked_entries[kind].add(rid)
    before = deepcopy(window.data)
    inspected = []

    def cancel(dialog):
        inspected.append(dialog.detailedText())
        assert rid in dialog.detailedText()
        assert dialog.defaultButton() == dialog.button(QMessageBox.Cancel)
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    window.remove_record(kind)
    assert getattr(window.data, kind) == getattr(before, kind)
    assert not window.dirty
    assert inspected and ("Routes" in inspected[0] or "Participants" in inspected[0])
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Yes)
    window.verify_change_toggle.setChecked(True)
    window.remove_record(kind)
    assert rid not in getattr(window.data, kind)
    assert window.dirty and window.verified
    if kind == "participants":
        assert before.participants[rid].route_id not in window.data.routes
    elif kind == "stops":
        assert all(rid not in route.stops for route in window.data.routes.values())
    else:
        assert all(p.route_id != rid for p in window.data.participants.values())


@pytest.mark.parametrize("kind", ["participants", "stops", "routes"])
def test_delete_all_button_clears_only_confirmed_table_and_affected_references(
    window, monkeypatch, kind
):
    from PySide6.QtWidgets import QMessageBox, QPushButton

    page = window.tabs.widget({"participants": 1, "stops": 2, "routes": 3}[kind])
    delete = next(
        widget for widget in page.findChildren(QPushButton) if widget.text() == "Delete all"
    )
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Cancel)
    delete.click()
    assert len(getattr(window.data, kind)) == 3
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Yes)
    delete.click()
    assert not getattr(window.data, kind) and window.tables[kind][0].rowCount() == 0
    assert window.dirty


def test_host_assignment_changes_reverify_routes_visiting_that_host(window):
    window.verify_change_toggle.setChecked(True)
    window.data.route_for("P002").main_stop_id = "S001"
    window.changed()
    assert all(
        "Host already assigned to other stop." in window.route_diagnostics[pid]["errors"]
        for pid in ("P001", "P003")
    )
    assert window.route_diagnostics["P002"]["errors"] == []


def test_picker_only_lists_completely_unassigned_pairings(window):
    window.data.participants["P004"] = Participant(id="P004", name="Unassigned")
    window.data.participants["P005"] = Participant(id="P005", name="Partial")
    window.data.assign_route("P005", ["S001", "", ""])
    dialog = ParticipantPicker(window.data, window)
    assert dialog.participants.count() == 1
    assert not dialog.select_button.isEnabled()
    dialog.participants.setCurrentRow(0)
    assert dialog.select_button.isEnabled()
    dialog.participants.itemDoubleClicked.emit(dialog.participants.item(0))
    assert dialog.result() == QDialog.Accepted
    assert dialog.participant_id == "P004"


def test_map_edits_revert_without_mutating_tables_and_save_updates_guests(window):
    original = window.data.route_for("P001").stops
    window.edit_route()
    session = window.draft.session
    window.map_bridge.drawSection(session, "P001", "P002")
    assert window.draft.stops == ["S001", "S002", ""]
    assert window.data.route_for("P001").stops == original
    assert not window.routes.isEnabled()
    assert window.save_route_button.isEnabled()
    window.revert_route()
    assert window.data.route_for("P001").stops == original
    assert window.routes.isEnabled()
    window.edit_route()
    window.map_bridge.drawSection(window.draft.session, "P001", "P002")
    window.save_route()
    assert window.data.route_for("P001").stops == ["S001", "S002", ""]
    assert "P001" not in window.data.stops["S003"].guests
    assert window.dirty
    window.map_bridge.clickHost(session, "P003")  # Stale message cannot mutate a saved route.
    assert window.data.route_for("P001").dessert_stop_id == ""


def test_adding_new_route_creates_persistent_empty_entry(window, monkeypatch):
    window.data.participants["P004"] = Participant(id="P004", name="New pairing")

    def select(dialog):
        dialog.participants.setCurrentRow(0)
        return QDialog.Accepted

    monkeypatch.setattr(ParticipantPicker, "exec", select)
    window.add_route()
    assert window.selected_route == "P004"
    assert "New pairing" in window.route_title.text()
    assert not window.data.route_for("P004").has_route
    assert window.dirty
    assert window.draft.participant_id == "P004"
    assert not window.routes.isEnabled()
    assert window.save_route_button.isEnabled()
    window.map_gesture(window.draft.session, "P001")
    assert not window.data.route_for("P004").has_route
    window.save_route()
    assert window.data.route_for("P004").appetizer_stop_id == "S001"
    assert "P004" in window.data.stops["S001"].guests


def test_empty_routes_stay_visible_and_remove_unlinks_participant(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window.data.assign_route("P001", ["", "", ""])
    window.refresh("P001")
    assert window.routes.count() == 3
    window.verify_routes()
    assert window.route_diagnostics["P001"]["errors"] == ["Empty route."]
    assert "Empty route." in window.routes.item(0).toolTip()
    assert ParticipantPicker(window.data, window).participants.count() == 0
    rid = window.data.participants["P001"].route_id
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Yes)
    window.remove_route_button.click()
    assert rid not in window.data.routes
    assert not window.data.participants["P001"].route_id
    assert window.routes.count() == 2 and window.tables["routes"][0].rowCount() == 2
    assert ParticipantPicker(window.data, window).participants.count() == 1
    window.refresh()
    assert window.data.route_for("P001") is None


def test_clear_routes_respects_cancel_and_keeps_participants(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Cancel)
    window.clear_routes_button.click()
    assert len(window.data.routes) == 3
    window.verify_change_toggle.setChecked(True)
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: QMessageBox.Yes)
    window.clear_routes_button.click()
    assert not window.data.routes and window.routes.count() == 0
    assert window.tables["routes"][0].rowCount() == 0
    assert len(window.data.participants) == 3 and not window.data.stops
    assert not window.route_diagnostics
    assert ParticipantPicker(window.data, window).participants.count() == 3
    assert window.dirty


def test_warning_toggles_filter_diagnostics_and_roundtrip_project(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    from cykelfest_routing.verification import WARNING_TYPES

    window.verify_change_toggle.setChecked(True)
    assert "Repeat meetups." in window.route_diagnostics["P001"]["warnings"]
    window.warning_toggles["Repeat meetups."].setChecked(True)
    assert not window.route_diagnostics["P001"]["warnings"]
    assert set(window.warning_toggles) == set(WARNING_TYPES)
    window.data.assign_route("P001", ["", "", ""])
    window.changed("P001")
    for toggle in window.warning_toggles.values():
        toggle.setChecked(True)
    assert window.route_diagnostics["P001"] == {"warnings": [], "errors": ["Empty route."]}
    path = tmp_path / "warnings.dsf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.save_project()
    for toggle in window.warning_toggles.values():
        toggle.blockSignals(True)
        toggle.setChecked(False)
        toggle.blockSignals(False)
    window.ignored_warnings.clear()
    window.load_project()
    assert all(toggle.isChecked() for toggle in window.warning_toggles.values())
    assert window.ignored_warnings == set(WARNING_TYPES)
    assert window.route_diagnostics["P001"] == {"warnings": [], "errors": ["Empty route."]}
    assert not window.dirty


def test_route_badges_include_both_severities_and_counts(window):
    window.set_route_diagnostics("P001", warnings=["First", "Second"], errors=["Conflict"])
    item = window.routes.item(0)
    assert "⚠ 2" in item.text()
    assert "⛔ 1" in item.text()
    assert "Warning: Second" in item.toolTip()
    assert "Error: Conflict" in item.toolTip()
    from PySide6.QtWidgets import QLabel

    entry = window.routes.itemWidget(item)
    assert entry.findChild(QLabel, "route_warnings").toolTip() == "First\nSecond"
    assert entry.findChild(QLabel, "route_errors").toolTip() == "Conflict"
    assert not entry.findChild(QLabel, "route_errors").pixmap().isNull()


def test_map_remove_is_draft_only_until_save(window):
    window.edit_route()
    window.map_bridge.removeStop(window.draft.session, 1)
    assert window.draft.stops == ["S001", "", "S003"]
    assert window.data.route_for("P001").main_stop_id == "S002"
    window.save_route()
    assert window.data.route_for("P001").main_stop_id == ""
    assert "P001" not in window.data.stops["S002"].guests


def test_settings_theme_switch_updates_tables_and_can_return_to_light(window):
    light = window.palette().color(window.palette().ColorRole.Window).name()
    window.dark_mode_toggle.setChecked(True)
    assert window.dark_mode
    assert window.palette().color(window.palette().ColorRole.Window).name() != light
    assert window.tables["participants"][0].item(0, 4).foreground().color().name() == "#68cfba"
    dialog = RecordDialog(window.data, "participants", parent=window)
    assert dialog.palette().color(dialog.palette().ColorRole.Window).name() == "#141d24"
    window.dark_mode_toggle.setChecked(False)
    assert window.palette().color(window.palette().ColorRole.Window).name() == light
    assert window.dark_mode_toggle.toolTip()
    assert window.verify_change_toggle.toolTip()
    assert window.delimiter_combo.toolTip()


def test_verify_on_change_checks_data_and_drafts_without_saving(window):
    window.verify_change_toggle.setChecked(True)
    window.data.route_for("P001").dessert_stop_id = "missing"
    window.changed()
    assert window.verified
    assert "Route contains stop(s) without a host." in window.routes.item(0).toolTip()
    window.edit_route()
    window.remove_map_stop(window.draft.session, 1)
    assert window.verified
    assert "Participant is not assigned all 3 stops." in window.route_details.toPlainText()
    assert window.data.route_for("P001").main_stop_id == "S002"
    window.revert_route()
    assert window.verified
    window.verify_change_toggle.setChecked(False)
    window.changed()
    assert not window.verified


def test_csv_delimiter_setting_is_used_by_import_and_export(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from cykelfest_routing.data import read_csv

    window.delimiter_combo.setCurrentIndex(window.delimiter_combo.findData(";"))
    path = tmp_path / "participants.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    window.export_csv("participants")
    assert path.read_text(encoding="utf-8-sig").startswith("id;name;address;")
    assert read_csv(path, "participants", ";") == window.data.participants
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.data.participants.clear()
    window.import_csv("participants")
    assert len(window.data.participants) == 3


def test_segment_preferences_defaults_bounds_and_reverification(window):
    assert window.minimum_segment.value() == 0.5
    assert window.maximum_segment.value() == 3.0
    window.verify_change_toggle.setChecked(True)
    window.maximum_segment.setValue(0.75)
    assert window.segment_preferences.maximum_km == 0.75
    assert "Long Route segment." in window.route_diagnostics["P001"]["warnings"]
    window.minimum_segment.setValue(10)
    assert window.minimum_segment.value() == 0.75
    window.verify_change_toggle.setChecked(False)
    window.maximum_segment.setValue(3)
    assert not window.verified


def test_route_badge_widgets_allow_mouse_selection(window, app):
    from PySide6.QtGui import QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel

    window.verify_routes()
    window.show()
    app.processEvents()

    def assert_highlight(index):
        assert window.selected_route == window.routes.item(index).data(Qt.UserRole)
        for row_index in range(window.routes.count()):
            row = window.routes.itemWidget(window.routes.item(row_index))
            expected = QPalette.Highlight if row_index == index else QPalette.Base
            assert row.backgroundRole() == expected

    assert_highlight(0)
    for index in (1, 2, 0, 2):
        row = window.routes.itemWidget(window.routes.item(index))
        QTest.mouseClick(row.findChild(QLabel), Qt.LeftButton)
        assert_highlight(index)
        assert window.data.participants[window.selected_route].name in window.route_title.text()
    window.routes.setFocus()
    QTest.keyClick(window.routes, Qt.Key_Up)
    assert_highlight(1)
    window.routes.setCurrentRow(0)
    assert_highlight(0)


def test_auto_verifies_all_shared_stop_routes_but_not_unaffected_routes(window, monkeypatch):
    from cykelfest_routing import gui

    window.data.participants["P004"] = Participant(id="P004", name="Independent")
    window.verify_change_toggle.setChecked(True)
    calls = []
    original = gui.verify_route

    def track(data, pid, preferences, ignored_warnings=()):
        calls.append(pid)
        return original(data, pid, preferences, ignored_warnings)

    monkeypatch.setattr(gui, "verify_route", track)
    window.data.stops["S001"].guests = []
    window.changed()
    assert set(calls) == {"P001", "P002", "P003"}
    calls.clear()
    window.edit_route()
    window.remove_map_stop(window.draft.session, 1)
    assert set(calls) == {"P001", "P002", "P003"}
    calls.clear()
    window.revert_route()
    assert set(calls) == {"P001", "P002", "P003"}


def test_course_dropdown_safe_edit_and_save_revert(window):
    window.data.participants["P004"] = Participant(id="P004", name="Available")
    menu = window.course_controls[1][2].menu()
    window.populate_stop_menu(1, menu)
    assert {action.data() for action in menu.actions() if action.data()} == {"P002", "P004"}
    next(action for action in menu.actions() if action.data() == "P004").trigger()
    assert window.draft.host_at(1) == "P004"
    assert window.draft.stops[0] == "S001" and window.draft.stops[2] == "S003"
    assert window.data.route_for("P001").main_stop_id == "S002"
    window.revert_route()
    assert window.data.route_for("P001").main_stop_id == "S002"
    window.safe_edit_toggle.setChecked(False)
    window.populate_stop_menu(1, menu)
    assert {action.data() for action in menu.actions() if action.data()} == set(
        window.data.participants
    )
    next(action for action in menu.actions() if action.data() == "P003").trigger()
    assert not window.draft.safe_edit
    assert window.draft.host_at(1) == "P003"
    window.safe_edit_toggle.setChecked(True)
    assert window.draft.safe_edit
    window.save_route()
    assert window.data.stops[window.data.route_for("P001").main_stop_id].host == "P003"


def test_course_center_uses_current_draft_coordinates(window, monkeypatch):
    from types import SimpleNamespace

    scripts = []
    original_map = window.map
    page = SimpleNamespace(runJavaScript=scripts.append)
    monkeypatch.setattr(window, "map", SimpleNamespace(page=lambda: page))
    window.enable_map = True
    window.center_stop(1)
    assert "flyTo([59.337, 18.05]" in scripts[-1]
    window.enable_map = False
    monkeypatch.setattr(window, "map", original_map)
    window.safe_edit_toggle.setChecked(False)
    window.replace_route_stop(1, "P003")
    monkeypatch.setattr(window, "map", SimpleNamespace(page=lambda: page))
    window.enable_map = True
    window.center_stop(1)
    assert "flyTo([59.315, 18.075]" in scripts[-1]
    window.enable_map = False


@pytest.mark.parametrize("use_selection", [True, False])
def test_find_addresses_runs_background_worker_and_only_fills_missing_coordinates(
    window, monkeypatch, tmp_path, app, use_selection
):
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox

    from cykelfest_routing import gui
    from cykelfest_routing.geocoding import AddressWorker

    window.data.participants["P004"] = Participant(id="P004", name="New", address="Street")
    window.data.participants["P005"] = Participant(id="P005", name="Empty address")
    window.data.participants["P006"] = Participant(
        id="P006", name="Unchecked", address="Skip this address"
    )
    requested = []

    class Provider:
        def geocode(self, address, **kwargs):
            from types import SimpleNamespace

            requested.append(address)
            return SimpleNamespace(latitude=59.31, longitude=18.02)

    def worker(addresses, cache, parent):
        return AddressWorker(
            addresses, tmp_path / "cache.json", parent, geocoder=Provider(), interval=0
        )

    monkeypatch.setattr(gui, "AddressWorker", worker)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    original = window.data.participants["P001"].latitude
    window.verify_change_toggle.setChecked(True)
    window.checked_entries["participants"] = {"P001", "P004", "P005"} if use_selection else set()
    window.find_addresses_button.click()
    timer = QElapsedTimer()
    timer.start()
    while window.address_worker is not None and timer.elapsed() < 5000:
        app.processEvents()
        QTest.qWait(10)
    assert window.address_worker is None
    assert requested == (["Street"] if use_selection else ["Street", "Skip this address"])
    assert window.data.participants["P004"].latitude == 59.31
    assert window.data.participants["P001"].latitude == original
    assert window.data.participants["P005"].latitude is None
    assert window.data.participants["P006"].latitude == (None if use_selection else 59.31)
    assert window.dirty and window.verified
    assert window.find_addresses_button.isEnabled()


def test_lookup_does_not_overwrite_participant_edits_or_replacements(window, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    participant = Participant(id="P004", name="New", address="Old address")
    window.data.participants["P004"] = participant
    window.address_lookup_data = window.data
    window.address_lookup_records = {"P004": participant}
    window.address_blank_count = 0
    window.address_progress = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    report = {
        "results": [("P004", "Old address", [59.3, 18.1])],
        "problems": [],
        "cancelled": False,
    }
    participant.address = "New address"
    window.address_lookup_results(report)
    assert participant.latitude is None
    window.data.participants["P004"] = Participant(
        id="P004", name="Replacement", address="Old address"
    )
    window.address_lookup_results(report)
    assert window.data.participants["P004"].latitude is None


def test_allergies_editor_results_button_and_solution_summary(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from cykelfest_routing.data import read_csv

    participant = window.data.participants["P001"]
    dialog = RecordDialog(window.data, "participants", participant, window)
    dialog.fields["allergies"].setText("tree nuts, cow milk")
    dialog.save()
    assert dialog.result_record.allergies == "tree nuts, cow milk"
    participant.allergies = dialog.result_record.allergies
    window.refresh()
    assert window.tables["participants"][0].item(0, 5).text() == participant.allergies
    assert window.export_results_button.text() == "Export results"
    assert "Average total distance" in window.solution_info.toPlainText()
    window.verify_routes()
    assert "Counts show affected routes" in window.solution_info.toPlainText()
    path = tmp_path / "results.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    window.export_results_button.click()
    assert "tree nuts, cow milk" in path.read_text(encoding="utf-8-sig")
    # Existing participant CSVs without the new optional field still import.
    path.write_text("name,address\nNew Pair,New Street\n", encoding="utf-8")
    assert next(iter(read_csv(path, "participants").values())).allergies == ""
