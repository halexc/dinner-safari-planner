import json

import pytest

from cykelfest_routing.data import demo_data
from cykelfest_routing.project import ProjectSettings, load_project, save_project


def test_project_roundtrip_preserves_all_tables_settings_and_conflicts(tmp_path):
    data = demo_data()
    data.stops["S003"].host = ""
    data.route_for("P001").main_stop_id = "missing"
    settings = ProjectSettings(
        safe_edit=False,
        minimum_segment_km=1.25,
        maximum_segment_km=6,
    )
    path = tmp_path / "event.dsf"
    save_project(path, data, settings)
    restored, preferences = load_project(path)
    for kind in ("participants", "stops", "routes"):
        assert getattr(restored, kind) == getattr(data, kind)
    assert preferences == settings
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2


def test_warning_minimization_settings_roundtrip_and_legacy_defaults(tmp_path):
    from cykelfest_routing.verification import WARNING_TYPES

    warning = "Repeat meetups."
    settings = ProjectSettings(minimize_warning_counts={warning: False})
    assert all(settings.minimize_warning_counts[name] for name in WARNING_TYPES if name != warning)
    path = tmp_path / "event.dsf"
    save_project(path, demo_data(), settings)
    assert load_project(path)[1].minimize_warning_counts == settings.minimize_warning_counts
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["settings"].pop("minimize_warning_counts")
    path.write_text(json.dumps(contents), encoding="utf-8")
    assert all(load_project(path)[1].minimize_warning_counts.values())
    with pytest.raises(ValueError):
        ProjectSettings(minimize_warning_counts={"unknown": False})
    with pytest.raises(ValueError):
        ProjectSettings(minimize_warning_counts={warning: "false"})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(version=99),
        lambda p: p["settings"].update(minimum_segment_km=4, maximum_segment_km=3),
        lambda p: p["participants"].append(p["participants"][0]),
        lambda p: p["routes"].pop(),
    ],
)
def test_invalid_projects_are_rejected(tmp_path, mutate):
    path = tmp_path / "event.dsf"
    save_project(path, demo_data(), ProjectSettings())
    content = json.loads(path.read_text(encoding="utf-8"))
    mutate(content)
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        load_project(path)


def test_failed_save_preserves_existing_project(tmp_path, monkeypatch):
    from cykelfest_routing import project

    path = tmp_path / "event.dsf"
    path.write_text("previous project", encoding="utf-8")

    def fail(*args):
        raise OSError("Cannot replace destination")

    monkeypatch.setattr(project.os, "replace", fail)
    with pytest.raises(OSError):
        save_project(path, demo_data(), ProjectSettings())
    assert path.read_text(encoding="utf-8") == "previous project"
    assert list(tmp_path.iterdir()) == [path]


def test_legacy_project_migrates_without_system_preferences(tmp_path):
    path = tmp_path / "legacy.dsf"
    save_project(path, demo_data(), ProjectSettings(safe_edit=False))
    content = json.loads(path.read_text(encoding="utf-8"))
    content["version"] = 1
    content["settings"].update(dark_mode=True, verify_on_change=True, csv_delimiter=";")
    path.write_text(json.dumps(content), encoding="utf-8")
    data, settings = load_project(path)
    assert len(data.routes) == 3
    assert settings == ProjectSettings(safe_edit=False)


def test_project_roundtrip_preserves_empty_and_absent_routes_and_warning_preferences(tmp_path):
    data = demo_data()
    data.remove_route("P001")
    data.assign_route("P002", ["", "", ""])
    settings = ProjectSettings(ignored_warnings={"Repeat meetups.", "Participant is not hosting."})
    path = tmp_path / "event.dsf"
    save_project(path, data, settings)
    restored, loaded_settings = load_project(path)
    restored.ensure_routes()
    assert restored.route_for("P001") is None
    assert restored.route_for("P002") is not None and not restored.route_for("P002").has_route
    assert restored.routes == data.routes and loaded_settings == settings
    with pytest.raises(ValueError, match="Unknown warning"):
        ProjectSettings(ignored_warnings={"Empty route."})


def test_solver_preferences_roundtrip_and_legacy_defaults(tmp_path):
    from cykelfest_routing.verification import WARNING_TYPES

    settings = ProjectSettings(
        respect_existing_routes=True,
        warning_multipliers={"Repeat meetups.": 2.345, "Short Route segment.": 0},
    )
    path = tmp_path / "weights.dsf"
    save_project(path, demo_data(), settings)
    assert load_project(path)[1] == settings
    content = json.loads(path.read_text())
    content["settings"].pop("respect_existing_routes")
    content["settings"].pop("warning_multipliers")
    path.write_text(json.dumps(content))
    restored = load_project(path)[1]
    assert not restored.respect_existing_routes
    assert restored.warning_multipliers == dict.fromkeys(WARNING_TYPES, 1)


@pytest.mark.parametrize("value", [-0.01, 5.01, float("nan"), float("inf")])
def test_invalid_warning_multipliers_are_rejected(value):
    with pytest.raises(ValueError):
        ProjectSettings(warning_multipliers={"Repeat meetups.": value})
