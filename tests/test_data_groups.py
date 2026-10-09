import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from cykelfest_routing.collaboration import CollaborationSession, decode_snapshot, snapshot
from cykelfest_routing.data import DataGroup, demo_data
from cykelfest_routing.gui import MainWindow
from cykelfest_routing.project import ProjectSettings, load_project, save_project


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        demo_data(),
        enable_map=False,
        preferences=QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat),
    )
    yield window
    window.dirty = False
    window.draft = None
    window.close()
    assert app is not None


def test_checkbox_ranges_sorting_and_last_entry(window, monkeypatch):
    table = window.tables["participants"][0]
    window.check_entry("participants", 0)
    window.check_entry("participants", 2, shift=True)
    assert window.checked_entries["participants"] == {"P001", "P002", "P003"}
    assert window.selected_record("participants") == "P003"
    window.check_entry("participants", 0, shift=True)
    assert not window.checked_entries["participants"]
    table.sortItems(1, Qt.DescendingOrder)
    window.check_entry("participants", 0)
    window.refresh()
    assert window.checked_entries["participants"] == {"P003"}
    assert table.item(0, 0).checkState() == Qt.Checked
    removed = []
    monkeypatch.setattr(window, "confirm_data_deletion", lambda kind, ids: removed.extend(ids))
    window.check_entry("participants", 1)
    window.remove_record("participants")
    assert set(removed) == {"P002", "P003"}


def test_groups_shared_membership_filters_and_selection(window):
    group = DataGroup(id="group-a", name="Friends", color="#ff8800")
    window.data.groups[group.id] = group
    window.selected_group = group.id
    window.checked_entries["participants"] = {"P001"}
    window.checked_entries["stops"] = {"S002"}
    window.checked_entries["routes"] = {"R-00003"}
    window.group_action("assign")
    assert group.participants == ["P001"] and group.stops == ["S002"]
    assert all(listing.item(0).text() == "Friends" for listing in window.group_lists)
    window.group_action("deselect")
    assert not any(window.checked_entries.values())
    window.group_action("select")
    assert window.checked_entries["routes"] == {"R-00003"}
    table = window.tables["participants"][0]
    window.group_filters["participants"].setCurrentIndex(1)
    assert not table.isRowHidden(0) and table.isRowHidden(1)
    window.jump_to("participants", "P002")
    assert window.group_filters["participants"].currentData() is None
    assert not table.isRowHidden(1)
    window.group_action("unbind")
    assert not group.participants and not group.stops and not group.routes


def test_filtered_shift_skips_hidden_rows(window):
    table = window.tables["participants"][0]
    table.setRowHidden(1, True)
    window.check_entry("participants", 0)
    window.check_entry("participants", 2, shift=True)
    assert window.checked_entries["participants"] == {"P001", "P003"}


def test_actual_checkbox_clicks_and_shift(window):
    from PySide6.QtTest import QTest

    window.tabs.setCurrentIndex(1)
    window.resize(1400, 850)
    window.show()
    QApplication.processEvents()
    table = window.tables["participants"][0]
    QTest.mouseClick(
        table.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        table.visualItemRect(table.item(0, 0)).center(),
    )
    QTest.mouseClick(
        table.viewport(),
        Qt.LeftButton,
        Qt.ShiftModifier,
        table.visualItemRect(table.item(2, 0)).center(),
    )
    assert window.checked_entries["participants"] == {"P001", "P002", "P003"}
    assert window.selected_record("participants") == "P003"
    QTest.mouseClick(
        table.viewport(),
        Qt.LeftButton,
        Qt.ShiftModifier,
        table.visualItemRect(table.item(0, 0)).center(),
    )
    assert not window.checked_entries["participants"]


def test_group_metadata_edit_and_deletion_cleanup(window, monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit, QToolButton

    window.data.groups["g"] = DataGroup(
        id="g", name="Original", participants=["P001"], routes=["R-00001"]
    )
    window.refresh()
    window.tabs.setCurrentIndex(1)
    window.show()
    QApplication.processEvents()
    window.edit_group("g")
    editor = window.group_lists[0].findChild(QLineEdit)
    assert editor is not None
    editor.setText("Updated")
    QTest.keyClick(editor, Qt.Key_Return)
    QApplication.processEvents()
    window.edit_group("g", color=True)
    choices = window.group_color_popup.findChildren(QToolButton)
    assert len(choices) == 9
    choices[0].click()
    assert window.data.groups["g"].name == "Updated"
    assert window.data.groups["g"].color == "#59a9dc"
    window.data.delete_records("participants", ["P001"])
    window.changed()
    assert not window.data.groups["g"].participants and not window.data.groups["g"].routes


def test_instant_groups_numbering_and_filter_icons(window):
    window.add_group()
    window.add_group()
    assert [group.name for group in window.data.groups.values()] == ["Group 001", "Group 002"]
    for combo in window.group_filters.values():
        assert not combo.itemIcon(0).isNull()
        assert not combo.itemIcon(1).isNull()


def test_header_checkbox_selects_whole_table(window):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    window.tabs.setCurrentIndex(1)
    window.show()
    QApplication.processEvents()
    table = window.tables["participants"][0]
    table.setRowHidden(1, True)
    header = table.horizontalHeader()
    QTest.mouseClick(
        header.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        QPoint(header.sectionSize(0) // 2, header.height() // 2),
    )
    assert window.checked_entries["participants"] == set(window.data.participants)
    QTest.mouseClick(
        header.viewport(),
        Qt.LeftButton,
        Qt.NoModifier,
        QPoint(header.sectionSize(0) // 2, header.height() // 2),
    )
    assert not window.checked_entries["participants"]


def test_map_dropdowns_equal_width_and_group_toggle_default(window):
    window.show()
    QApplication.processEvents()
    assert not window.color_by_groups.isChecked()
    assert abs(window.map_mode.width() - window.group_filters["map"].width()) <= 1


def test_filtered_map_excludes_selected_route_without_crashing(window):
    from cykelfest_routing.map_view import map_html

    window.data.groups["g"] = DataGroup(id="g", name="Empty")
    window.refresh()
    window.group_filters["map"].setCurrentIndex(1)
    filtered = window.filtered_map_data(window.data)
    assert not filtered.participants
    assert "leaflet" in map_html(filtered, "P001", "All routes", True, focus_route=True)


def test_load_resets_local_checks_and_filters(window):
    window.data.groups["g"] = DataGroup(id="g", name="Group", participants=["P001"])
    window.refresh()
    window.group_filters["participants"].setCurrentIndex(1)
    window.checked_entries["participants"].add("P001")
    window.apply_project(demo_data(), ProjectSettings())
    assert not any(window.checked_entries.values())
    assert all(combo.currentData() is None for combo in window.group_filters.values())


def test_map_group_filter_includes_complete_paths(window):
    window.data.groups["g"] = DataGroup(id="g", name="Route", routes=["R-00001"])
    window.refresh()
    window.group_filters["map"].setCurrentIndex(1)
    filtered = window.filtered_map_data(window.data)
    assert set(filtered.routes) == {"R-00001"}
    assert set(filtered.stops) == {"S001", "S002", "S003"}
    assert len(filtered.participants) == 3
    assert len(window.data.routes) == 3
    assert not hasattr(window, "pre_gen_button")


def test_groups_project_round_trip_and_collaboration(tmp_path):
    data = demo_data()
    data.groups["g"] = DataGroup(
        id="g", name="Mixed", participants=["P001"], stops=["S002"], routes=["R-00001"]
    )
    path = tmp_path / "groups.dsf"
    save_project(path, data, ProjectSettings())
    loaded, settings = load_project(path)
    assert loaded.groups == data.groups
    session = CollaborationSession()
    session.state = snapshot(loaded, settings)
    edited = deepcopy(loaded)
    edited.groups["g"].name = "Updated"
    from cykelfest_routing.collaboration import difference

    session.execute(
        "client", "patch", {"changes": difference(session.state, snapshot(edited, settings))}
    )
    restored, _ = decode_snapshot(session.state)
    assert restored.groups["g"].name == "Updated"
    session.timer.stop()
    session.deleteLater()
