from copy import deepcopy

import pytest

from cykelfest_routing.data import Participant, demo_data
from cykelfest_routing.route_edit import RouteDraft


def test_draft_does_not_clear_unrelated_imported_guests_without_routes():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Unrouted guest")
    data.stops["S003"].guests.append("P004")
    draft = RouteDraft(data, "P001")
    draft.replace(1, "P002")
    assert "P004" in draft.data.stops["S003"].guests
    assert draft.data.route_for("P004") is None


def test_click_fills_first_gap_without_overwriting_dessert():
    data = demo_data()
    data.assign_route("P001", ["S001", "", "S003"])
    draft = RouteDraft(data, "P001")
    draft.click("P002")
    assert draft.stops == ["S001", "S002", "S003"]
    assert data.route_for("P001").main_stop_id == ""


def test_drag_from_main_continues_but_other_start_resets():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.draw("P002", "P004")
    assert draft.stops[:2] == ["S001", "S002"]
    assert draft.data.stops[draft.stops[2]].host == "P004"
    draft.draw("P004", "P002")
    assert draft.data.stops[draft.stops[0]].host == "P004"
    assert draft.stops[1:] == ["S002", ""]


def test_away_host_is_rejected_and_gesture_is_atomic():
    data = demo_data()
    draft = RouteDraft(data, "P001")
    assert draft.eligible("P002", 1)
    assert not draft.eligible("P002", 0)
    previous = deepcopy(draft.data.participants)
    with pytest.raises(ValueError, match="away during Appetizer"):
        draft.draw("P003", "P002")  # P003 is away at appetizer; entire gesture rejected.
    assert draft.data.participants == previous


def test_invalid_drag_endpoint_does_not_clear_existing_route():
    draft = RouteDraft(demo_data(), "P001")
    previous = draft.stops[:]
    with pytest.raises(ValueError, match="away during Main dish"):
        draft.draw("P001", "P003")
    assert draft.stops == previous


def test_commit_creates_only_used_course_stops_and_correct_membership():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.draw("P004", "P002")
    abandoned = draft.stops[0]
    draft.draw("P001", "P004")
    new_main = draft.stops[1]
    assert new_main not in data.stops
    draft.commit(data)
    assert abandoned not in data.stops
    assert data.stops[new_main].course == "Main dish"
    assert data.stops[new_main].guests == ["P001"]
    assert "P001" not in data.stops["S002"].guests
    assert "P001" not in data.stops["S003"].guests


def test_counts_and_eligibility_follow_draft_state():
    data = demo_data()
    draft = RouteDraft(data, "P001")
    draft.draw("P001", "P002")
    hosts = {host["id"]: host for host in draft.payload()["hosts"]}
    assert hosts["P001"]["own"]
    assert hosts["P003"]["guests"][2] == 1  # Edited pairing removed from dessert in preview.
    assert len(data.stops["S003"].guests) == 2
    assert not hosts["P002"]["eligible"][0]
    assert hosts["P002"]["eligible"][1]


def test_unassigned_host_receives_matching_course_only_on_commit():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.draw("P002", "P004")
    sid = draft.stops[2]
    assert draft.data.route_for("P004").stops == ["", "", sid]
    assert data.route_for("P004") is None
    draft.commit(data)
    assert data.route_for("P004").stops == ["", "", sid]
    assert "P004" not in data.stops[sid].guests
    assert data.stops[sid].guests == ["P001"]


def test_remove_preserves_other_courses_and_releases_automatic_host_assignment():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.draw("P002", "P004")
    removed = draft.stops[2]
    draft.remove(2)
    assert draft.stops == ["S001", "S002", ""]
    assert draft.data.route_for("P004") is None
    draft.commit(data)
    assert removed not in data.stops
    assert data.route_for("P004") is None
    assert data.route_for("P002").main_stop_id == "S002"


def test_abandoned_section_does_not_commit_automatic_host_reservation():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.draw("P004", "P002")
    assert draft.data.route_for("P004").appetizer_stop_id
    draft.draw("P001", "P002")
    draft.commit(data)
    assert data.route_for("P004") is None


def test_same_route_can_still_have_a_new_host_assignment_to_commit():
    data = demo_data()
    data.route_for("P002").main_stop_id = ""
    draft = RouteDraft(data, "P001")
    draft.remove(1)
    draft.click("P002")
    assert draft.stops == draft.original
    assert draft.changed
    draft.commit(data)
    assert data.route_for("P002").main_stop_id == "S002"


def test_edit_can_save_while_another_course_has_an_unknown_imported_host():
    data = demo_data()
    data.stops["S003"].host = "unknown"
    draft = RouteDraft(data, "P001")
    draft.remove(1)
    draft.commit(data)
    assert data.route_for("P001").stops == ["S001", "", "S003"]
    assert any("unknown host" in issue for issue in data.issues("P001"))


def test_specific_course_replacement_preserves_other_courses_and_host_reservations():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Available")
    draft = RouteDraft(data, "P001")
    draft.replace(1, "P004")
    assert draft.stops[0] == "S001" and draft.stops[2] == "S003"
    sid = draft.stops[1]
    assert sid == "S-00001"
    assert draft.data.route_for("P004").main_stop_id == sid
    assert data.route_for("P001").main_stop_id == "S002"
    draft.commit(data)
    assert data.route_for("P004").main_stop_id == sid
    assert "P001" not in data.stops["S002"].guests


def test_safe_edit_controls_choices_and_every_assignment_path():
    draft = RouteDraft(demo_data(), "P001")
    assert [host.id for host, _ in draft.choices(0)] == ["P001"]
    with pytest.raises(ValueError, match="away"):
        draft.replace(0, "P002")
    draft.safe_edit = False
    assert len(draft.choices(0)) == 3
    assert all(all(host["eligible"]) for host in draft.payload()["hosts"])
    draft.replace(0, "P002")
    assert draft.host_at(0) == "P002"
    # Unsafe edits allow visiting an away host without overwriting that host's route.
    assert draft.data.route_for("P002").appetizer_stop_id == "S001"
    draft.draw("P003", "P001")
    assert draft.host_at(0) == "P003" and draft.host_at(1) == "P001"
    draft.click("P002")
    assert draft.host_at(2) == "P002"
