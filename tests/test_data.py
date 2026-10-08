import pytest

from cykelfest_routing.data import (
    DinnerData,
    Participant,
    Stop,
    csv_source,
    demo_data,
    infer_csv_mapping,
    next_record_id,
    parse_csv,
    read_csv,
    write_csv,
)


def test_generated_ids_use_five_digits_and_skip_existing_records():
    assert next_record_id({"P001": None, "P-00001": None, "P-00003": None}, "P") == "P-00004"
    assert next_record_id({}, "S") == "S-00001"
    with pytest.raises(ValueError, match="No P-XXXXX"):
        next_record_id({"P-99999": None}, "P")


@pytest.mark.parametrize(
    "kind,prefix,content",
    [
        ("participants", "P", "name,address\nFirst,Street\nSecond,Other\n"),
        ("stops", "S", "host,course\nP001,Appetizer\nP002,Dessert\n"),
        ("routes", "R", "Appetizer,Main Dish,Dessert\nS001,S002,S003\n,,\n"),
    ],
)
def test_csv_without_id_generates_ids_for_each_table(tmp_path, kind, prefix, content):
    path = tmp_path / "data.csv"
    path.write_text(content)
    records = read_csv(path, kind)
    assert list(records) == [f"{prefix}-00001", f"{prefix}-00002"]


def test_blank_csv_ids_avoid_later_explicit_ids_and_preserve_imported_ids(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("id,name\n,First\nP-00001,Second\n,Third\nlegacy,Fourth\n")
    records = read_csv(path, "participants")
    assert list(records) == ["P-00002", "P-00001", "P-00003", "legacy"]


def test_csv_mapping_uses_positions_and_defaults_without_rewriting_references(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("People;Location;Host route\nFirst;Street;R-00009\n")
    source = csv_source(path, ";")
    _, review = infer_csv_mapping(source, "participants")
    assert review
    records = parse_csv(source, "participants", mapping={"name": 0, "address": 1, "route_id": 2})
    assert records["P-00001"].route_id == "R-00009"
    assert records["P-00001"].address == "Street"
    assert records["P-00001"].latitude is None


def test_duplicate_headers_require_mapping_but_can_be_selected_by_position(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Name,Name\nFirst,Second\n")
    source = csv_source(path)
    assert infer_csv_mapping(source, "participants")[1]
    assert parse_csv(source, "participants", mapping={"name": 1})["P-00001"].name == "Second"
    with pytest.raises(ValueError, match="only one"):
        parse_csv(source, "participants", mapping={"name": 0, "address": 0})


def test_malformed_mapped_rows_and_missing_required_name_are_rejected(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Name,Address\nFirst,Street,Extra\n")
    with pytest.raises(ValueError, match="CSV row 2: expected 2 columns"):
        read_csv(path, "participants", mapping={"name": 0, "address": 1})
    path.write_text("Address\nStreet\n")
    with pytest.raises(ValueError, match="Name / pairing"):
        read_csv(path, "participants", mapping={"address": 0})


from cykelfest_routing.map_view import map_html


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_csv_roundtrip_preserves_ids_unicode_and_route(tmp_path, delimiter):
    data = demo_data()
    data.participants["001"] = Participant(
        id="001", name="Åsa & Björn, Team", address="Street\nSecond line"
    )
    data.ensure_routes()
    for kind in ("participants", "stops", "routes"):
        path = tmp_path / f"{kind}.csv"
        records = getattr(data, kind)
        write_csv(path, records, kind, delimiter)
        assert read_csv(path, kind, delimiter) == records


def test_invalid_csv_reports_row_and_does_not_return_partial_data(tmp_path):
    path = tmp_path / "participants.csv"
    path.write_text("id,name\n001,First\n001,Duplicate\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV row 3: Duplicate ID"):
        read_csv(path, "participants")
    path.write_text("id,name,latitude,longitude\n001,Name,59,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="both latitude and longitude"):
        read_csv(path, "participants")


def test_route_edit_updates_membership_and_remove_keeps_records():
    data = demo_data()
    data.stops["S004"] = Stop(id="S004", host="P002", course="Dessert")
    data.assign_route("P001", ["S001", "S002", "S004"])
    assert "P001" not in data.stops["S001"].guests  # Host is not its own guest.
    assert "P001" not in data.stops["S003"].guests
    assert "P001" in data.stops["S004"].guests
    assert data.route_for("P001").dessert_stop_id == "S004"
    data.assign_route("P001", ["", "", ""])
    assert not data.route_for("P001").has_route
    assert all("P001" not in stop.guests for stop in data.stops.values())
    assert len(data.stops) == 4


def test_validation_reports_broken_course_host_and_membership():
    data = demo_data()
    assert data.issues("P001") == []
    data.route_for("P001").main_stop_id = "S003"
    data.stops["S003"].host = "unknown"
    data.stops["S003"].guests.remove("P001")
    issues = "\n".join(data.issues("P001"))
    assert "is a Dessert stop" in issues
    assert "unknown host" in issues
    assert "absent from the guest list" in issues
    assert "visited more than once" in issues


def test_map_does_not_bridge_missing_middle_stop():
    data = demo_data()
    data.participants["P002"].latitude = None
    data.participants["P002"].longitude = None
    html = map_html(data, "P001", "Selected route", False)
    assert "L.polyline" not in html
    assert "openstreetmap.org" in html
    assert "map-fallback" in html
    assert "L.polyline" not in map_html(DinnerData(), None, "All routes", True)


def test_map_escapes_imported_html_and_javascript_delimiters():
    data = demo_data()
    data.participants["P001"].name = "<script>alert(1)</script> `${alert(2)} \\"
    html = map_html(data, "P001", "Selected route", True)
    assert "<script>alert(1)</script>" not in html
    assert "${alert(2)}" not in html
    assert "&#96;" in html
    assert "&#36;" in html


def test_invalid_route_length_leaves_existing_assignment_unchanged():
    data = demo_data()
    original_stops = data.route_for("P001").stops
    original_guests = {sid: stop.guests[:] for sid, stop in data.stops.items()}
    with pytest.raises(ValueError, match="exactly three"):
        data.assign_route("P001", ["S001"])
    assert data.route_for("P001").stops == original_stops
    assert {sid: stop.guests for sid, stop in data.stops.items()} == original_guests


def test_routes_are_one_to_one_and_participants_do_not_store_assignments():
    data = demo_data()
    assert len(data.routes) == len(data.participants)
    assert {p.route_id for p in data.participants.values()} == set(data.routes)
    assert data.route_for("P001").id == "R-00001"
    assert "appetizer_stop_id" not in data.participants["P001"].model_dump()
    data.participants["P004"] = Participant(id="P004", name="New")
    data.ensure_routes()
    assert data.route_for("P004") is None
    assert data.create_route("P004").id == "R-00004"
    del data.participants["P004"]
    data.ensure_routes()
    assert "R-00004" not in data.routes


def test_legacy_participant_csv_migrates_and_new_csv_tables_restore_links(tmp_path):
    legacy = tmp_path / "legacy.csv"
    legacy.write_text(
        "id,name,appetizer_stop_id,main_stop_id,dessert_stop_id\nP001,First,S001,S002,S003\n",
        encoding="utf-8",
    )
    data = DinnerData()
    data.replace_table("participants", read_csv(legacy, "participants"))
    assert data.route_for("P001").stops == ["S001", "S002", "S003"]
    for kind in ("participants", "stops", "routes"):
        write_csv(tmp_path / f"{kind}.csv", getattr(data, kind), kind)
    restored = DinnerData()
    for kind in ("participants", "stops", "routes"):
        restored.replace_table(kind, read_csv(tmp_path / f"{kind}.csv", kind))
    assert restored.participants == data.participants
    assert restored.routes == data.routes


def test_invalid_csv_route_relationship_is_atomic():
    from cykelfest_routing.data import Route

    data = demo_data()
    original = data.route_for("P001").model_copy(deep=True)
    with pytest.raises(ValueError, match="exactly the Route IDs"):
        data.replace_table("routes", {"R-99999": Route(id="R-99999")})
    assert data.route_for("P001") == original
    participants = {pid: p.model_copy(deep=True) for pid, p in data.participants.items()}
    participants["P002"].route_id = participants["P001"].route_id
    with pytest.raises(ValueError, match="different route ID"):
        data.replace_table("participants", participants)
    assert data.participants["P002"].route_id == "R-00002"


def test_removing_routes_keeps_participants_stops_and_does_not_recreate_entries():
    data = demo_data()
    rid = data.route_for("P001").id
    data.remove_route("P001")
    data.ensure_routes()
    assert rid not in data.routes and data.participants["P001"].route_id == ""
    assert data.route_for("P001") is None
    assert data.coordinates("P001") == [None, None, None]
    assert all("P001" not in stop.guests for stop in data.stops.values())
    data.create_route("P001")
    assert data.route_for("P001") is not None and not data.route_for("P001").has_route
    data.clear_routes()
    data.ensure_routes()
    assert not data.routes and all(not p.route_id for p in data.participants.values())
    assert len(data.participants) == len(data.stops) == 3
    assert all(not stop.guests for stop in data.stops.values())


def test_force_delete_participant_removes_own_route_and_all_host_guest_references():
    data = demo_data()
    rid = data.route_for("P001").id
    data.delete_records("participants", ["P001"])
    assert "P001" not in data.participants and rid not in data.routes
    assert data.stops["S001"].host == ""
    assert all("P001" not in stop.guests for stop in data.stops.values())
    assert len(data.stops) == 3  # Shared stops survive, including a now-hostless stop.
    assert all(data.route_stops(pid)[0] == "S001" for pid in data.participants)
    data.ensure_routes()
    assert rid not in data.routes


def test_force_delete_stop_resets_every_course_reference_without_removing_routes():
    data = demo_data()
    data.delete_records("stops", ["S002"])
    assert "S002" not in data.stops and len(data.routes) == 3
    assert all(route.stops == ["S001", "", "S003"] for route in data.routes.values())


def test_deleting_route_removes_only_its_unshared_stops_and_clears_owner_link():
    data = demo_data()
    data.assign_route("P002", ["", "S002", "S003"])
    data.assign_route("P003", ["", "S002", "S003"])
    data.stops["unused"] = Stop(id="unused")
    data.delete_records("routes", [data.route_for("P001").id])
    assert data.route_for("P001") is None and not data.participants["P001"].route_id
    assert set(data.stops) == {"S002", "S003", "unused"}
    assert all("P001" not in stop.guests for stop in data.stops.values())
    assert len(data.routes) == 2


@pytest.mark.parametrize("kind", ["participants", "stops", "routes"])
def test_delete_all_table_entries_clears_references(kind):
    data = demo_data()
    data.delete_records(kind, list(getattr(data, kind)))
    assert not getattr(data, kind)
    if kind == "participants":
        assert not data.routes and not data.stops
    elif kind == "stops":
        assert all(not route.has_route for route in data.routes.values())
        assert len(data.participants) == len(data.routes) == 3
    else:
        assert all(not p.route_id for p in data.participants.values())
        assert len(data.participants) == 3 and not data.stops


def test_deleting_unassigned_participant_preserves_other_unassigned_guest_references():
    data = demo_data()
    data.clear_routes()
    data.stops["S001"].guests = ["P002"]
    data.stops["empty"] = Stop(id="empty")
    data.delete_records("participants", ["P001"])
    assert data.stops["S001"].host == "" and data.stops["S001"].guests == ["P002"]
    assert "empty" in data.stops
