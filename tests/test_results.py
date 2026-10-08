import csv
import json

import pytest
from geopy.distance import geodesic

from cykelfest_routing.data import demo_data, read_csv, write_csv
from cykelfest_routing.project import ProjectSettings, load_project, save_project
from cykelfest_routing.results import result_rows, solution_summary, write_results


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_allergies_csv_and_project_roundtrip(tmp_path, delimiter):
    data = demo_data()
    data.participants["P001"].allergies = "tree nuts, cow’s milk"
    path = tmp_path / "participants.csv"
    write_csv(path, data.participants, "participants", delimiter)
    assert read_csv(path, "participants", delimiter) == data.participants
    project = tmp_path / "event.dsf"
    save_project(project, data, ProjectSettings())
    assert load_project(project)[0].participants == data.participants
    content = json.loads(project.read_text(encoding="utf-8"))
    for participant in content["participants"]:
        participant.pop("allergies")
    project.write_text(json.dumps(content), encoding="utf-8")
    assert all(p.allergies == "" for p in load_project(project)[0].participants.values())


def test_results_include_host_and_guest_allergies_and_quoted_addresses(tmp_path):
    data = demo_data()
    for pid, allergies in zip(
        data.participants, ["tree nuts, milk", "shell fish", ""], strict=True
    ):
        data.participants[pid].allergies = allergies
    first = data.participants["P001"]
    first.address = "Street 1, Stockholm"
    rows = list(result_rows(data))
    assert rows[0]["Appetizer"] == "(H) Street 1, Stockholm"
    assert not rows[0]["Main Dish"].startswith("(H)")
    assert rows[0]["Allergies"] == "tree nuts, milk, shell fish"
    path = tmp_path / "results.csv"
    write_results(path, data)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        assert list(csv.DictReader(stream)) == rows
    data.remove_route("P001")
    row = next(iter(result_rows(data)))
    assert row["Appetizer"] == row["Main Dish"] == row["Dessert"] == row["Allergies"] == ""


def test_summary_ignores_missing_legs_and_incomplete_totals():
    data = demo_data()
    points = data.coordinates("P001")
    lengths = [geodesic(points[i], points[i + 1]).km for i in range(2)]
    diagnostics = {
        "P001": {"warnings": ["Short Route segment."], "errors": []},
        "P002": {"warnings": ["Short Route segment."], "errors": ["Empty route."]},
    }
    summary = solution_summary(data, diagnostics)
    assert summary["Shortest leg"] > 0
    assert summary["Longest leg"] >= max(lengths)
    assert summary["warnings"]["Short Route segment."] == 2
    assert summary["errors"]["Empty route."] == 1
    for pid in data.participants:
        data.route_for(pid).main_stop_id = ""
    summary = solution_summary(data, {})
    assert summary["Shortest leg"] is None
    assert summary["Average total distance"] is None
