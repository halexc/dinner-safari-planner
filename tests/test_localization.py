import ast
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer, QSettings
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QProgressDialog

from cykelfest_routing.data import demo_data
from cykelfest_routing.gui import MainWindow, RecordDialog
from cykelfest_routing.localization import CATALOG, LANGUAGES, set_language, tr, translate_message
from cykelfest_routing.map_view import map_html
from cykelfest_routing.project import ProjectSettings, save_project
from cykelfest_routing.route_edit import RouteDraft


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        demo_data(),
        enable_map=False,
        preferences=QSettings(str(tmp_path / "system.ini"), QSettings.IniFormat),
    )
    yield window
    window.draft = None
    window.dirty = False
    window.close()
    set_language("en")
    assert app is not None


def test_catalogs_have_all_languages_and_preserve_template_arguments():
    for source, translations in CATALOG.items():
        assert set(translations) == set(LANGUAGES) - {"en"}
        for translated in translations.values():
            assert translated
            assert sorted(re.findall(r"\{\d+\}", source)) == sorted(
                re.findall(r"\{\d+\}", translated)
            ), source
    tree = ast.parse(Path("src/cykelfest_routing/gui.py").read_text(encoding="utf-8"))
    missing = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "tr"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value not in CATALOG
    }
    assert not missing


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_switch_updates_gui_and_preserves_data(window, language, tmp_path):
    before = window.data_snapshot()
    window.data.participants["P001"].name = "Save"
    window.refresh("P002")
    window.map_mode.setCurrentIndex(window.map_mode.findData("All routes"))
    window.show_hosts.setChecked(False)
    window.resize(1300, 850)
    before = window.data_snapshot()
    window.minimum_segment.setValue(0.75)
    window.warning_sliders["Repeat meetups."].setValue(1234)
    window.warning_minimization_toggles["Repeat meetups."].setChecked(False)
    window.respect_routes_toggle.setChecked(True)
    dirty = window.dirty
    window.tabs.setCurrentIndex(4)
    window.language_combo.setCurrentIndex(window.language_combo.findData(language))
    assert window.language == language
    assert window.preferences.value("system/language", "en") == language
    assert window.save_project_button.text() == tr("Save Project")
    assert window.tabs.tabText(0) == tr("Map")
    assert window.tabs.currentIndex() == 4
    assert window.data_snapshot() == before
    assert window.dirty == dirty
    assert window.selected_route == "P002"
    assert window.map_mode.currentData() == "All routes"
    assert not window.show_hosts.isChecked()
    assert window.size().width() == 1300
    assert window.minimum_segment.value() == 0.75
    assert window.warning_sliders["Repeat meetups."].value() == 1234
    assert not window.warning_minimization_toggles["Repeat meetups."].isChecked()
    assert not window.minimize_warning_counts["Repeat meetups."]
    assert window.respect_existing_routes
    table = window.tables["participants"][0]
    assert table.item(0, 2).text() == "Save"  # User data must never be translated.
    route_table = window.tables["routes"][0]
    assert route_table.horizontalHeaderItem(2).text() == tr("Appetizer")
    window.verify_routes()
    assert tr("Repeat meetups.") in window.solution_info.toPlainText()
    project = tmp_path / "event.dsf"
    save_project(project, window.data, ProjectSettings())
    assert "language" not in json.loads(project.read_text(encoding="utf-8"))["settings"]


def test_language_survives_restart_and_english_brand_is_bike_party(window):
    assert "Bike Party" in window.windowTitle()
    window.language_combo.setCurrentIndex(window.language_combo.findData("de"))
    restarted = MainWindow(demo_data(), enable_map=False, preferences=window.preferences)
    assert restarted.language == "de"
    assert restarted.save_project_button.text() == "Projekt speichern"
    restarted.close()


def test_localized_course_edit_stores_english_course_code(window):
    window.language_combo.setCurrentIndex(window.language_combo.findData("fr"))
    dialog = RecordDialog(window.data, "stops", window.data.stops["S001"], window)
    course = dialog.fields["course"]
    course.setCurrentIndex(course.findData("Main dish"))
    assert course.currentText() == "Plat principal"
    dialog.save()
    assert dialog.result_record.course == "Main dish"
    assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).text() != "Cancel"


def test_language_switch_keeps_unsaved_map_draft(window):
    window.refresh("P001")
    window.edit_route()
    window.draft.remove(2)
    draft = window.draft
    before = window.data_snapshot()
    window.language_combo.setCurrentIndex(window.language_combo.findData("sv"))
    assert window.draft is draft
    assert window.data_snapshot() == before
    assert window.save_route_button.isEnabled()
    assert "Efterrätt" in window.course_controls[2][0].text()


@pytest.mark.parametrize("language", ["de", "fr", "es", "sv"])
def test_solver_and_map_messages_are_localized(window, language):
    window.language_combo.setCurrentIndex(window.language_combo.findData(language))
    assert translate_message("Preparing distances and assignment constraints…") == tr(
        "Preparing distances and assignment constraints…"
    )
    assert translate_message("Minimizing warnings…") == tr("Minimizing warnings") + "…"
    assert translate_message("Pre-Gen: 2/3 routes") == tr("Pre-Gen: {0}/{1} routes", "2", "3")
    assert translate_message("P001: invalid Main dish stop.") == tr(
        "{0}: invalid {1} stop.", "P001", tr("Main dish")
    )
    window.solver_progress = QProgressDialog()
    window.solver_elapsed = QElapsedTimer()
    window.solver_elapsed.start()
    window.update_solver_phase("Balancing travel…")
    assert tr("Balancing travel") in window.solver_progress.labelText()
    assert "Elapsed:" not in window.solver_progress.labelText()
    window.solver_progress.close()
    html = map_html(
        window.data, "P001", "Selected route", True, draft=RouteDraft(window.data, "P001")
    )
    assert "window.cykelfestI18n" in html
    assert json.dumps(tr("Remove appetizer")) in html


def test_language_change_is_deferred_while_background_worker_runs(window):
    window.address_worker = SimpleNamespace()
    window.language_combo.setCurrentIndex(window.language_combo.findData("es"))
    assert window.language == "en"
    assert window.language_combo.currentData() == "en"
    window.address_worker = None


def test_validation_and_csv_mapping_labels_are_localized(window, tmp_path):
    from cykelfest_routing.data import read_csv
    from cykelfest_routing.gui import CSVMappingDialog
    from cykelfest_routing.localization import error_text, field_label

    window.language_combo.setCurrentIndex(window.language_combo.findData("de"))
    path = tmp_path / "participants.csv"
    path.write_text("name,latitude,longitude\nPair,not-a-number,12\n", encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        read_csv(path, "participants")
    message = error_text(failure.value)
    assert "CSV-Zeile 2" in message
    assert "Breitengrad" in message
    assert "Eine Zahl eingeben." in message
    assert "Input should" not in message
    dialog = CSVMappingDialog(path, "participants", ",", window)
    assert dialog.form.labelForField(dialog.column_combos["address"]).text() == field_label(
        "address"
    )
    assert dialog.form.labelForField(dialog.column_combos["longitude"]).text() == "Längengrad"


def test_combined_solver_validation_errors_are_localized(window):
    window.language_combo.setCurrentIndex(window.language_combo.findData("sv"))
    message = translate_message(
        "P001: existing route cannot be kept: Empty route. Host already assigned to other stop."
    )
    assert "P001" in message
    assert tr("Empty route.") in message
    assert tr("Host already assigned to other stop.") in message
