from geopy.distance import geodesic

from cykelfest_routing.data import demo_data
from cykelfest_routing.verification import SegmentPreferences, verify_route


def test_balanced_sample_reports_repeat_meetups():
    assert verify_route(demo_data(), "P001", SegmentPreferences()) == {
        "warnings": ["Repeat meetups."],
        "errors": [],
    }


def test_guest_and_length_warnings_are_reported_once_per_category():
    data = demo_data()
    data.stops["S001"].guests = []
    data.stops["S002"].guests = []
    data.stops["S003"].guests = ["a", "b", "c"]
    first, second = [
        geodesic(a, b).km for a, b in zip(data.coordinates("P001"), data.coordinates("P001")[1:])
    ]
    result = verify_route(
        data, "P001", SegmentPreferences((first + second) / 2, (first + second) / 2)
    )
    assert result["warnings"] == [
        "Route contains stops with few guests.",
        "Route contains stops with many guests.",
        "Short Route segment.",
        "Long Route segment.",
    ]


def test_distance_thresholds_are_strict_and_missing_coordinates_do_not_bridge():
    data = demo_data()
    lengths = [
        geodesic(a, b).km for a, b in zip(data.coordinates("P001"), data.coordinates("P001")[1:])
    ]
    assert verify_route(data, "P001", SegmentPreferences(min(lengths), max(lengths)))[
        "warnings"
    ] == ["Repeat meetups."]
    data.participants["P002"].latitude = None
    data.participants["P002"].longitude = None
    assert verify_route(data, "P001", SegmentPreferences(100, 100))["warnings"] == [
        "Repeat meetups."
    ]


def test_hosting_missing_assignment_and_host_errors():
    data = demo_data()
    data.stops["S002"].host = "P001"
    assert (
        "Participant is repeat host."
        in verify_route(data, "P001", SegmentPreferences())["warnings"]
    )
    data.stops["S001"].host = ""
    data.stops["S002"].host = "unknown"
    data.route_for("P001").dessert_stop_id = "missing"
    result = verify_route(data, "P001", SegmentPreferences())
    assert result["errors"] == ["Route contains stop(s) without a host."]
    assert "Participant is not hosting." in result["warnings"]
    assert "Participant is not assigned all 3 stops." in result["warnings"]
    data.assign_route("P001", ["", "", ""])
    assert verify_route(data, "P001", SegmentPreferences()) == {
        "warnings": ["Participant is not hosting.", "Participant is not assigned all 3 stops."],
        "errors": ["Empty route."],
    }


def test_host_assigned_elsewhere_as_guest_or_host_is_an_error():
    data = demo_data()
    data.route_for("P002").main_stop_id = "S001"
    assert verify_route(data, "P001", SegmentPreferences())["errors"] == [
        "Host already assigned to other stop."
    ]
    data.stops["S001"].host = "P002"
    assert verify_route(data, "P001", SegmentPreferences())["errors"] == [
        "Host already assigned to other stop."
    ]
    data.route_for("P002").main_stop_id = ""
    assert verify_route(data, "P001", SegmentPreferences())["errors"] == []


def test_repeat_meetups_require_two_known_participants_at_two_distinct_stops():
    from cykelfest_routing.data import Participant

    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Fourth")
    for sid, guest in zip(data.stops, ("P002", "P003", "P004"), strict=True):
        data.stops[sid].host = "P001"
        data.stops[sid].guests = [guest, guest]
    assert "Repeat meetups." not in verify_route(data, "P001", SegmentPreferences())["warnings"]
    data.stops["S002"].guests.append("P002")
    assert "Repeat meetups." in verify_route(data, "P001", SegmentPreferences())["warnings"]
    data.assign_route("P001", ["S001", "S001", ""])
    assert "Repeat meetups." not in verify_route(data, "P001", SegmentPreferences())["warnings"]


def test_ignored_warnings_never_hide_errors_and_unrouted_participants_are_skipped():
    from cykelfest_routing.verification import WARNING_TYPES

    data = demo_data()
    data.assign_route("P001", ["", "", ""])
    assert verify_route(data, "P001", SegmentPreferences(), WARNING_TYPES) == {
        "warnings": [],
        "errors": ["Empty route."],
    }
    data.remove_route("P001")
    assert verify_route(data, "P001", SegmentPreferences()) == {"warnings": [], "errors": []}


def test_long_distance_error_is_strict_and_cannot_be_ignored():
    from cykelfest_routing.verification import WARNING_TYPES

    data = demo_data()
    longest = max(
        geodesic(a, b).km for a, b in zip(data.coordinates("P001"), data.coordinates("P001")[1:])
    )
    assert (
        "Route segment exceeds hard maximum distance."
        not in verify_route(data, "P001", SegmentPreferences(0, longest / 3))["errors"]
    )
    result = verify_route(data, "P001", SegmentPreferences(0, longest / 3 - 0.001), WARNING_TYPES)
    assert "Route segment exceeds hard maximum distance." in result["errors"]
    assert not result["warnings"]
