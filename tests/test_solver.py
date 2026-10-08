from copy import deepcopy
from itertools import product
from threading import Event

import pytest

from cykelfest_routing.data import COURSES, DinnerData, Participant, Stop, demo_data
from cykelfest_routing.solver import pre_generate_routes, solve_routes, validate_assignment
from cykelfest_routing.verification import WARNING_TYPES, SegmentPreferences, verify_route


def test_solver_returns_complete_verified_assignment_without_mutating_input():
    data = demo_data()
    before = deepcopy(data)
    result = solve_routes(data, SegmentPreferences(), maximum_time=5)
    assert result.status == "OPTIMAL" and len(result.objectives) == 4
    validate_assignment(result.data, SegmentPreferences())
    for kind in ("participants", "stops", "routes"):
        assert getattr(data, kind) == getattr(before, kind)
    assert {p.route_id for p in result.data.participants.values()} == set(before.routes)
    assert all(
        not verify_route(result.data, pid, SegmentPreferences())["errors"]
        for pid in data.participants
    )


def seed_data(count=9):
    data = DinnerData()
    data.participants = {
        f"p{i}": Participant(
            id=f"p{i}",
            name=f"Pair {i}",
            latitude=59.3 + (i // 3) * 0.006,
            longitude=18 + (i % 3) * 0.01,
        )
        for i in range(count)
    }
    return data


def test_pre_gen_random_disjoint_bounded_routes_and_solver_completion():
    from random import Random

    data = seed_data()
    preferences = SegmentPreferences(0.3, 2)
    first = pre_generate_routes(data, preferences, rng=Random(1))
    second = pre_generate_routes(data, preferences, rng=Random(2))
    assert first.data is not None and "2/2" in first.message
    routes = {
        pid: first.data.route_for(pid)
        for pid in data.participants
        if (route := first.data.route_for(pid)) and all(route.stops)
    }
    assert len(routes) == 2
    hosts = []
    for pid, route in routes.items():
        route_hosts = [first.data.stops[sid].host for sid in route.stops]
        assert route_hosts[0] == pid
        hosts.extend(route_hosts)
        diagnostics = verify_route(first.data, pid, preferences)
        assert not diagnostics["errors"]
        assert "Short Route segment." not in diagnostics["warnings"]
        assert "Long Route segment." not in diagnostics["warnings"]
        for slot, host in enumerate(route_hosts):
            assert first.data.route_stops(host)[slot] == route.stops[slot]
    assert len(hosts) == len(set(hosts)) == 6
    assert first.data.participants != second.data.participants
    assert not data.routes and not data.stops
    completed = solve_routes(first.data, preferences, respect_existing_routes=True, maximum_time=5)
    assert completed.data is not None
    validate_assignment(completed.data, preferences)
    assert all(completed.data.route_for(pid) == route for pid, route in routes.items())


def test_pre_gen_preserves_existing_assignments_and_cancellation():
    from random import Random

    data = seed_data()
    data.stops["old"] = Stop(id="old", host="p0", course="Dessert")
    data.assign_route("p0", ["", "", "old"])
    before = deepcopy(data)
    result = pre_generate_routes(data, SegmentPreferences(0.3, 2), rng=Random(1))
    assert result.data is not None and result.data.route_stops("p0")[2] == "old"
    assert data.routes == before.routes and data.stops == before.stops
    cancelled = Event()
    cancelled.set()
    assert (
        pre_generate_routes(data, SegmentPreferences(), cancelled=cancelled).status == "CANCELLED"
    )
    expired = pre_generate_routes(data, SegmentPreferences(), maximum_time=0.000001)
    assert expired.data is None


def test_pre_gen_no_feasible_triplets_never_changes_input():
    data = seed_data()
    before = deepcopy(data)
    result = pre_generate_routes(data, SegmentPreferences(10, 12))
    assert result.status == "INFEASIBLE" and result.data is None
    assert data.participants == before.participants and not data.routes and not data.stops


def test_pre_gen_rejects_host_assignments_that_would_create_errors():
    data = seed_data(4)
    data.stops["away"] = Stop(id="away", host="missing", course="Main dish")
    for pid in ("p1", "p2", "p3"):
        data.assign_route(pid, ["", "away", ""])
    result = pre_generate_routes(data, SegmentPreferences(0, 3))
    assert result.data is None  # No possible main-course host is at home.


def test_hard_distance_limit_forbids_transitions_between_distant_addresses():
    data = DinnerData()
    data.participants = {
        "a": Participant(id="a", name="A", latitude=59, longitude=18),
        "b": Participant(id="b", name="B", latitude=60, longitude=18),
    }
    preferences = SegmentPreferences(0.5, 1)
    result = solve_routes(data, preferences, WARNING_TYPES, maximum_time=5)
    assert result.data is not None
    for pid in data.participants:
        hosts = [result.data.stops[sid].host for sid in result.data.route_stops(pid)]
        assert len(set(hosts)) == 1
    validate_assignment(result.data, preferences)
    # Ignoring long-distance warnings cannot disable the hard cap.
    stop = result.data.stops[result.data.route_stops("a")[1]]
    stop.host = "a" if stop.host == "b" else "b"
    stop.guests = [pid for pid in data.participants if pid != stop.host]
    with pytest.raises(ValueError, match="hard maximum distance"):
        validate_assignment(result.data, preferences)


def test_solver_creates_missing_routes_and_keeps_unselected_stops_empty():
    data = demo_data()
    data.clear_routes()
    data.stops["unused"] = Stop(id="unused", host="unknown", guests=["ghost"])
    result = solve_routes(data, SegmentPreferences(), maximum_time=5)
    assert len(result.data.routes) == 3
    assert result.data.stops["unused"].guests == []
    assert not data.routes and data.stops["unused"].guests == ["ghost"]


def test_missing_coordinates_and_empty_input_are_reported():
    with pytest.raises(ValueError, match="Add participants"):
        solve_routes(DinnerData(), SegmentPreferences())
    data = demo_data()
    data.participants["P001"].latitude = None
    data.participants["P001"].longitude = None
    with pytest.raises(ValueError, match="P001"):
        solve_routes(data, SegmentPreferences())


def test_cancelled_and_timed_out_generation_leave_project_unchanged():
    data = demo_data()
    cancelled = Event()
    cancelled.set()
    assert solve_routes(data, SegmentPreferences(), cancelled=cancelled).status == "CANCELLED"
    assert solve_routes(data, SegmentPreferences(), maximum_time=0.000001).status == "UNKNOWN"
    assert len(data.routes) == 3


def test_ignored_warnings_remove_penalties_but_preserve_complete_routes():
    result = solve_routes(demo_data(), SegmentPreferences(), WARNING_TYPES, maximum_time=5)
    assert result.objectives[0] == 0
    assert all(
        not verify_route(result.data, pid, SegmentPreferences(), WARNING_TYPES)["warnings"]
        for pid in result.data.participants
    )
    validate_assignment(result.data, SegmentPreferences())


def test_warning_priority_matches_exhaustive_small_event():
    data = DinnerData()
    data.participants = {
        "a": Participant(id="a", name="A", latitude=59, longitude=18),
        "b": Participant(id="b", name="B", latitude=59.01, longitude=18),
    }
    preferences = SegmentPreferences()
    best = 100
    for assignment in product(range(2), repeat=6):
        routes = [assignment[:3], assignment[3:]]
        if any(routes[h][t] != h for route in routes for t, h in enumerate(route)):
            continue
        candidate = deepcopy(data)
        for h in range(2):
            for t, course in enumerate(COURSES):
                candidate.stops[f"{h}-{t}"] = Stop(
                    id=f"{h}-{t}", host=list(data.participants)[h], course=course
                )
        for p, pid in enumerate(data.participants):
            candidate.assign_route(pid, [f"{h}-{t}" for t, h in enumerate(routes[p])])
        active = {sid for route in candidate.routes.values() for sid in route.stops}
        sizes = [1 + len(candidate.stops[sid].guests) for sid in active]
        cost = sum(
            len(verify_route(candidate, pid, preferences)["warnings"]) for pid in data.participants
        ) + int(max(sizes) - min(sizes) > 1)
        best = min(best, cost)
    result = solve_routes(data, preferences, maximum_time=5)
    assert result.status == "OPTIMAL" and result.objectives[0] == best * 1000


def test_nine_pairings_can_host_once_in_balanced_groups_without_repeat_meetups():
    data = DinnerData()
    data.participants = {
        str(i): Participant(id=str(i), name=f"Pair {i}", latitude=59.33, longitude=18.07)
        for i in range(9)
    }
    result = solve_routes(data, SegmentPreferences(), maximum_time=5)
    assert result.status == "OPTIMAL"
    for pid in data.participants:
        # Co-located addresses necessarily violate the preferred minimum only.
        assert verify_route(result.data, pid, SegmentPreferences()) == {
            "warnings": ["Short Route segment."],
            "errors": [],
        }
    used = {sid for route in result.data.routes.values() for sid in route.stops}
    assert len(used) == 9 and all(len(result.data.stops[sid].guests) == 2 for sid in used)


def test_later_search_timeout_keeps_the_previously_valid_incumbent(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    original = solver.cp_model.CpSolver
    calls = []

    class TimedOut:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    def factory():
        calls.append(True)
        return original() if len(calls) == 1 else TimedOut()

    monkeypatch.setattr(solver.cp_model, "CpSolver", factory)
    result = solve_routes(demo_data(), SegmentPreferences(), maximum_time=5)
    assert len(calls) == 4 and result.status == "FEASIBLE"
    validate_assignment(result.data, SegmentPreferences())


def test_respecting_existing_routes_preserves_exact_stop_ids_and_assigns_new_participants():
    data = demo_data()
    # A duplicate candidate at the same address must not replace the locked ID.
    data.stops = {
        "alternative": Stop(id="alternative", host="P001", course="Appetizer")
    } | data.stops
    data.participants["new"] = Participant(id="new", name="New", latitude=59.33, longitude=18.07)
    before = deepcopy(data.routes)
    result = solve_routes(data, SegmentPreferences(), respect_existing_routes=True, maximum_time=5)
    assert result.data is not None
    assert all(result.data.routes[rid] == route for rid, route in before.items())
    assert all(result.data.route_stops("new"))
    validate_assignment(result.data, SegmentPreferences())
    assert data.route_for("new") is None


@pytest.mark.parametrize("assigned", list(product((False, True), repeat=3)))
def test_respect_routes_completes_any_empty_slots_without_changing_assigned_stops(assigned):
    data = demo_data()
    stops = [sid if keep else "" for sid, keep in zip(data.route_stops("P001"), assigned)]
    data.assign_route("P001", stops)
    before = deepcopy(data)
    result = solve_routes(data, SegmentPreferences(), respect_existing_routes=True, maximum_time=5)
    assert result.data is not None
    validate_assignment(result.data, SegmentPreferences())
    assert result.data.route_for("P001").id == before.route_for("P001").id
    for pid in data.participants:
        for old, new in zip(before.route_stops(pid), result.data.route_stops(pid), strict=True):
            assert not old or old == new
    assert data.routes == before.routes and data.stops == before.stops


def test_partial_route_forces_unassigned_host_home_and_preserves_exact_stop_id():
    data = demo_data()
    data.clear_routes()
    data.stops = {"alternative": Stop(id="alternative", host="P001")} | data.stops
    data.assign_route("P002", ["S001", "", "S003"])
    before = deepcopy(data)
    result = solve_routes(data, SegmentPreferences(), respect_existing_routes=True, maximum_time=5)
    assert result.data is not None
    assert result.data.route_stops("P002")[::2] == ["S001", "S003"]
    assert result.data.route_stops("P001")[0] == "S001"
    assert result.data.route_stops("P003")[2] == "S003"
    assert result.data.route_for("P002").id == before.route_for("P002").id
    validate_assignment(result.data, SegmentPreferences())
    assert data.routes == before.routes and data.stops == before.stops


def test_infeasible_partial_route_is_not_changed_or_completed():
    data = DinnerData()
    data.participants = {
        "a": Participant(id="a", name="A", latitude=59, longitude=18),
        "b": Participant(id="b", name="B", latitude=60, longitude=18),
    }
    data.stops = {
        "first": Stop(id="first", host="a", course="Appetizer"),
        "last": Stop(id="last", host="b", course="Dessert"),
    }
    data.assign_route("a", ["first", "", "last"])
    before = deepcopy(data)
    result = solve_routes(
        data, SegmentPreferences(0.5, 1), respect_existing_routes=True, maximum_time=5
    )
    assert result.status == "INFEASIBLE" and result.data is None
    assert data.routes == before.routes and data.stops == before.stops


def test_invalid_and_conflicting_locked_routes_are_reported():
    data = demo_data()
    data.route_for("P002").main_stop_id = "S001"
    with pytest.raises(ValueError, match="cannot be kept|invalid"):
        solve_routes(data, SegmentPreferences(), respect_existing_routes=True)
    data = demo_data()
    data.assign_route("P001", ["missing", "", ""])
    with pytest.raises(ValueError, match="invalid Appetizer"):
        solve_routes(data, SegmentPreferences(), respect_existing_routes=True)


def test_respect_routes_does_not_relax_the_hard_distance_cap():
    with pytest.raises(ValueError, match="hard maximum distance"):
        solve_routes(demo_data(), SegmentPreferences(0, 0.1), respect_existing_routes=True)


def test_fractional_multipliers_match_verified_weighted_warning_cost():
    weights = {
        "Repeat meetups.": 2.345,
        "Short Route segment.": 0.25,
        "Participant is not hosting.": 4.5,
    }
    result = solve_routes(
        demo_data(), SegmentPreferences(), warning_multipliers=weights, maximum_time=5
    )
    cost = sum(
        round(weights.get(warning, 1) * 1000)
        for pid in result.data.participants
        for warning in verify_route(result.data, pid, SegmentPreferences())["warnings"]
    )
    used = {sid for route in result.data.routes.values() for sid in route.stops}
    sizes = [1 + len(result.data.stops[sid].guests) for sid in used]
    cost += 1000 * int(max(sizes) - min(sizes) > 1)
    assert result.objectives[0] == cost


def test_zero_multipliers_disable_penalties_without_hiding_warnings():
    weights = dict.fromkeys(WARNING_TYPES, 0)
    result = solve_routes(
        demo_data(), SegmentPreferences(), warning_multipliers=weights, maximum_time=5
    )
    assert result.objectives[0] == 0
    assert any(
        verify_route(result.data, pid, SegmentPreferences())["warnings"]
        for pid in result.data.participants
    )
    validate_assignment(result.data, SegmentPreferences())


def test_warning_minimization_toggle_keeps_secondary_penalties_and_diagnostics():
    warning = "Repeat meetups."
    options = {
        "respect_existing_routes": True,
        "warning_multipliers": {warning: 2.5},
        "maximum_time": 5,
    }
    enabled = solve_routes(demo_data(), SegmentPreferences(), **options)
    disabled = solve_routes(
        demo_data(), SegmentPreferences(), minimize_warning_counts={warning: False}, **options
    )
    assert enabled.status == disabled.status == "OPTIMAL"
    assert enabled.objectives[0] - disabled.objectives[0] == 3 * 2500
    assert enabled.objectives[1:] == disabled.objectives[1:]
    assert warning in verify_route(disabled.data, "P001", SegmentPreferences())["warnings"]


def test_increasing_repeat_meetup_penalty_changes_assignment_preferences():
    data = demo_data()
    baseline = solve_routes(data, SegmentPreferences(), maximum_time=5)
    weighted = solve_routes(
        data, SegmentPreferences(), warning_multipliers={"Repeat meetups.": 5}, maximum_time=5
    )

    def repeat_count(result):
        return sum(
            "Repeat meetups." in verify_route(result.data, pid, SegmentPreferences())["warnings"]
            for pid in data.participants
        )

    assert repeat_count(weighted) < repeat_count(baseline)


@pytest.mark.parametrize("minimize_counts", [True, False])
def test_search_timeout_returns_independently_validated_starting_assignment(
    monkeypatch, minimize_counts
):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    class NoSolution:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    monkeypatch.setattr(solver.cp_model, "CpSolver", NoSolution)
    data = seed_data(9)
    result = solve_routes(
        data,
        SegmentPreferences(),
        maximum_time=5,
        minimize_warning_counts=dict.fromkeys(WARNING_TYPES, minimize_counts),
    )
    assert result.status == "FEASIBLE" and result.data is not None
    validate_assignment(result.data, SegmentPreferences())
    assert not data.routes and not data.stops
    assert result.objectives[0] == sum(
        len(verify_route(result.data, pid, SegmentPreferences())["warnings"])
        * 1000
        * minimize_counts
        for pid in result.data.participants
    )  # Nine-participant seed has equal-size groups.


def test_fallback_preserves_exact_partial_route_assignments(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    class NoSolution:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    monkeypatch.setattr(solver.cp_model, "CpSolver", NoSolution)
    data = demo_data()
    data.assign_route("P001", ["S001", "", "S003"])
    before = deepcopy(data)
    result = solve_routes(data, SegmentPreferences(), respect_existing_routes=True)
    assert result.status == "FEASIBLE"
    validate_assignment(result.data, SegmentPreferences())
    for pid in data.participants:
        assert result.data.route_for(pid).id == before.route_for(pid).id
        assert all(
            not old or old == new
            for old, new in zip(before.route_stops(pid), result.data.route_stops(pid), strict=True)
        )


def test_large_event_restricted_search_does_not_claim_global_optimality():
    data = seed_data(45)
    result = solve_routes(data, SegmentPreferences(), maximum_time=0.5)
    assert result.status == "FEASIBLE" and result.data is not None
    validate_assignment(result.data, SegmentPreferences())


def test_distance_preparation_reuses_unique_coordinate_pairs(monkeypatch):
    from cykelfest_routing import solver

    original = solver.geodesic
    calls = []

    class Metric:
        def measure(self, first, second):
            calls.append((first, second))
            return original(first, second).km

    monkeypatch.setattr(solver, "geodesic", Metric)
    data = seed_data(9)
    # Three locations repeated three times: just three distinct pair calculations.
    for i, participant in enumerate(data.participants.values()):
        participant.latitude = 59.3 + (i % 3) * 0.005
        participant.longitude = 18
    result = solve_routes(data, SegmentPreferences(), maximum_time=5)
    assert result.data is not None and len(calls) == 3
    validate_assignment(result.data, SegmentPreferences())


def test_full_domain_pruning_proves_impossible_locked_bridge(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    class NoAssignment:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.INFEASIBLE

        def stop_search(self):
            pass

    monkeypatch.setattr(solver.cp_model, "CpSolver", NoAssignment)
    data = seed_data(45)
    data.stops["first"] = Stop(id="first", host="p1", course="Appetizer")
    data.stops["last"] = Stop(id="last", host="p2", course="Dessert")
    data.assign_route("p0", ["first", "", "last"])
    result = solve_routes(data, SegmentPreferences(0, 0.01), respect_existing_routes=True)
    assert result.status == "INFEASIBLE" and result.data is None


def test_stage_budgets_continue_after_unknown_and_keep_valid_seed(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    clock = [0.0]
    budgets = []

    class TimedOut:
        def __init__(self):
            self.parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            budgets.append(self.parameters.max_time_in_seconds)
            clock[0] += self.parameters.max_time_in_seconds
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    monkeypatch.setattr(solver, "monotonic", lambda: clock[0])
    monkeypatch.setattr(solver.cp_model, "CpSolver", TimedOut)
    result = solve_routes(demo_data(), SegmentPreferences(), maximum_time=30)
    assert budgets == pytest.approx([18, 9, 2.25, 0.75])
    assert result.status == "FEASIBLE"
    validate_assignment(result.data, SegmentPreferences())


def test_non_hosting_slider_penalty_remains_when_count_toggle_disabled():
    data = demo_data()
    for t, course in enumerate(COURSES):
        data.stops[f"home{t}"] = Stop(id=f"home{t}", host="P001", course=course)
    for pid in data.participants:
        data.assign_route(pid, ["home0", "home1", "home2"])
    multipliers = dict.fromkeys(WARNING_TYPES, 0)
    multipliers["Participant is not hosting."] = 5
    result = solve_routes(
        data,
        SegmentPreferences(),
        maximum_time=5,
        respect_existing_routes=True,
        warning_multipliers=multipliers,
        minimize_warning_counts=dict.fromkeys(WARNING_TYPES, False),
    )
    assert result.objectives[:2] == (0, 10_000_000)
    validate_assignment(result.data, SegmentPreferences())


def test_balancing_prefers_even_totals_and_even_course_legs():
    from cykelfest_routing.solver import _travel_score

    # Same longest route and same total travel; other route lengths differ.
    assert _travel_score([6000, 3000, 3000], [[3000, 1500, 1500]] * 2) < _travel_score(
        [6000, 5000, 1000], [[3000, 2500, 500]] * 2
    )
    # Same individual totals, but one assignment has markedly unequal legs.
    assert _travel_score([4000, 4000], [[2000, 2000], [2000, 2000]]) < _travel_score(
        [4000, 4000], [[500, 3500], [3500, 500]]
    )


@pytest.mark.parametrize("disable_counts", [False, True])
@pytest.mark.parametrize("count", [3, 9])
def test_model_objectives_match_independent_scoring_with_fixed_routes(disable_counts, count):
    from geopy.distance import geodesic

    from cykelfest_routing.solver import (
        _assignment_scores,
        _candidate_from_hosts,
        _grouped_assignment,
    )

    data = demo_data()
    if count == 9:
        data = seed_data()
        points = [(p.latitude, p.longitude) for p in data.participants.values()]
        matrix = [[geodesic(a, b).km for b in points] for a in points]
        data = _candidate_from_hosts(
            data,
            list(data.participants),
            _grouped_assignment(9, matrix, 9),
            {},
            SegmentPreferences(),
        )
    multipliers = {name: (i + 1) / 3 for i, name in enumerate(WARNING_TYPES)}
    multipliers = {name: round(value, 3) for name, value in multipliers.items()}
    result = solve_routes(
        data,
        SegmentPreferences(),
        maximum_time=5,
        respect_existing_routes=True,
        warning_multipliers=multipliers,
        minimize_warning_counts=dict.fromkeys(WARNING_TYPES, not disable_counts),
    )
    ids = list(data.participants)
    coordinates = [(p.latitude, p.longitude) for p in data.participants.values()]
    distances = [[geodesic(a, b).km for b in coordinates] for a in coordinates]
    rows = [
        [ids.index(result.data.stops[sid].host) for sid in result.data.route_stops(pid)]
        for pid in ids
    ]
    weights = {name: round(value * 1000) for name, value in multipliers.items()}
    counts = dict.fromkeys(WARNING_TYPES, 0) if disable_counts else weights
    assert result.objectives == _assignment_scores(
        rows, distances, SegmentPreferences(), weights, counts
    )


def test_unlocked_current_routes_are_retained_when_search_times_out(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    data = solve_routes(seed_data(), SegmentPreferences(), maximum_time=5).data
    ids = list(data.participants)
    before = [[data.stops[sid].host for sid in data.route_stops(pid)] for pid in ids]

    class NoSolution:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    # Disable competing constructive seeds to isolate the imported starting assignment.
    monkeypatch.setattr(solver, "_repair_seed", lambda *args: None)
    monkeypatch.setattr(solver.cp_model, "CpSolver", NoSolution)
    result = solve_routes(data, SegmentPreferences(), maximum_time=5)
    assert result.data is not None
    validate_assignment(result.data, SegmentPreferences())
    # A valid current assignment is considered even though it is not locked.
    from geopy.distance import geodesic

    coordinates = [(p.latitude, p.longitude) for p in data.participants.values()]
    distances = [[geodesic(a, b).km for b in coordinates] for a in coordinates]
    original_score = solver._assignment_scores(
        [[ids.index(h) for h in row] for row in before],
        distances,
        SegmentPreferences(),
        dict.fromkeys(WARNING_TYPES, 1000),
    )
    assert result.objectives <= original_score


def test_equal_warning_search_solution_cannot_replace_better_seed(monkeypatch):
    from types import SimpleNamespace

    from cykelfest_routing import solver

    original = solver.cp_model.CpSolver
    calls = []

    class WorseTie(original):
        def solve(self, model, callback=None):
            trial = model.clone()
            for index, variable in enumerate(trial.proto.variables):
                if variable.name.startswith("host_"):
                    p = int(variable.name.split("_")[1])
                    trial.add(trial.get_int_var_from_proto_index(index) == p)
            return super().solve(trial, callback)

    class NoSolution:
        parameters = SimpleNamespace()

        def solve(self, model, callback=None):
            return solver.cp_model.UNKNOWN

        def stop_search(self):
            pass

    def factory():
        calls.append(True)
        return WorseTie() if len(calls) == 1 else NoSolution()

    monkeypatch.setattr(solver.cp_model, "CpSolver", factory)
    counts = dict.fromkeys(WARNING_TYPES, False)
    counts["Short Route segment."] = True
    result = solve_routes(
        seed_data(),
        SegmentPreferences(2, 3),
        maximum_time=5,
        minimize_warning_counts=counts,
    )
    assert result.objectives[0] == 9000
    assert all(len(stop.guests) == 2 for stop in result.data.stops.values())
    validate_assignment(result.data, SegmentPreferences())


def test_candidate_domains_keep_seed_and_expand_around_course_locations():
    from cykelfest_routing.solver import _candidate_pools, _grouped_assignment

    n = 60
    distances = [[abs(p - q) * 0.1 for q in range(n)] for p in range(n)]
    preferences = SegmentPreferences(0.1, 2)
    rows = _grouped_assignment(n, distances, 6)
    small = _candidate_pools(n, distances, preferences, {}, rows, 12)
    large = _candidate_pools(n, distances, preferences, {}, rows, 24)
    assert sum(len(slot) for row in large for slot in row) > sum(
        len(slot) for row in small for slot in row
    )
    assert all(set(small[p][t]) <= set(large[p][t]) for p in range(n) for t in range(3))
    assert all(rows[p][t] in small[p][t] for p in range(n) for t in range(3))


def test_disabled_penalties_omit_warning_variables_and_distance_columns():
    from cykelfest_routing.solver import _build_model

    n = 3
    pools = [[tuple(range(n)) for _ in range(3)] for _ in range(n)]
    weights = dict.fromkeys(WARNING_TYPES, 0)
    model, _, _ = _build_model(
        pools, [[0] * n for _ in range(n)], SegmentPreferences(), {}, weights, weights, lambda: None
    )
    names = [v.name for v in model.proto.variables]
    assert not any(
        name.startswith(
            ("few_", "many_", "not_host_", "repeat_", "short_", "long_", "deficit_", "excess_")
        )
        for name in names
    )
    assert all(len(c.table.exprs) == 3 for c in model.proto.constraints if c.has_table())
