from cykelfest_routing.data import Participant, Stop, demo_data
from cykelfest_routing.map_view import STOP_OUTLINES, host_outlines, map_html
from cykelfest_routing.route_edit import RouteDraft


def test_host_outlines_follow_assigned_courses_and_multiple_courses():
    data = demo_data()
    data.participants["P004"] = Participant(id="P004", name="Unassigned")
    data.stops["unused"] = Stop(id="unused", host="P004")
    assert host_outlines(data) == {
        "P001": STOP_OUTLINES["Appetizer"],
        "P002": STOP_OUTLINES["Main dish"],
        "P003": STOP_OUTLINES["Dessert"],
        "P004": STOP_OUTLINES["No course"],
    }
    data.stops["dessert-home"] = Stop(id="dessert-home", host="P001", course="Dessert")
    data.assign_route("P001", ["S001", "S002", "dessert-home"])
    assert host_outlines(data)["P001"] == STOP_OUTLINES["Multiple courses"]


def test_editor_outlines_update_from_draft_without_changing_saved_routes():
    data = demo_data()
    draft = RouteDraft(data, "P001", safe_edit=False)
    draft.draw("P001", "P001")
    hosts = {host["id"]: host for host in draft.payload()["hosts"]}
    assert hosts["P001"]["outline"] == STOP_OUTLINES["Multiple courses"]
    assert host_outlines(data)["P001"] == STOP_OUTLINES["Appetizer"]


def test_route_focusing_uses_course_locations_instead_of_all_hosts():
    data = demo_data()
    data.participants["far"] = Participant(id="far", name="Far", latitude=60, longitude=19)
    normal = map_html(data, "P001", "All routes", True)
    focused = map_html(data, "P001", "All routes", True, focus_route=True)
    # FitBounds is emitted once by Folium; the fit icon's host list remains separate.
    normal_bounds = normal.split(".fitBounds(", 1)[1].split(");", 1)[0]
    focused_bounds = focused.split(".fitBounds(", 1)[1].split(");", 1)[0]
    assert "[60.0, 19.0]" in normal_bounds
    assert "[60.0, 19.0]" not in focused_bounds
    assert "bridge.selectRoute" in focused
    assert "bubblingMouseEvents" in focused
