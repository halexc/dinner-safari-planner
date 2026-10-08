"""Whole-event CP-SAT assignment on the application's straight-line distances."""

from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from math import ceil
from os import cpu_count
from random import Random
from threading import Event, Thread
from time import monotonic

from geopy.distance import geodesic
from ortools.sat.python import cp_model
from PySide6.QtCore import QThread, Signal

from .data import COURSES, Stop, next_record_id
from .project import ProjectSettings
from .verification import verify_route


@dataclass
class SolverResult:
    status: str
    message: str
    data: object = None
    objectives: tuple = ()
    elapsed: float = 0


def _assignment_scores(rows, distances, preferences, weights, warning_weights=None):
    """Evaluate the same four priorities without constructing a CP-SAT model."""
    groups = {}
    warning_weights = weights if warning_weights is None else warning_weights
    for p, row in enumerate(rows):
        for t, h in enumerate(row):
            groups.setdefault((h, t), set()).add(p)
    sizes = [len(group) for group in groups.values()]
    spread = max(sizes) - min(sizes)
    warnings = 1000 * int(spread > 1)
    severity = 500000 * max(0, spread - 1) + 1000 * spread
    lengths = []
    leg_lengths = [[], []]
    for p, row in enumerate(rows):
        sizes = [len(groups[h, t]) for t, h in enumerate(row)]
        hosting = sum(h == p for h in row)
        legs = [distances[row[t]][row[t + 1]] for t in range(2)]
        meetings = {}
        for t, h in enumerate(row):
            for q in groups[h, t] - {p}:
                meetings[q] = meetings.get(q, 0) + 1
        flags = {
            "Route contains stops with few guests.": any(size < 3 for size in sizes),
            "Route contains stops with many guests.": any(size > 3 for size in sizes),
            "Short Route segment.": any(d < preferences.minimum_km for d in legs),
            "Long Route segment.": any(d > preferences.maximum_km for d in legs),
            "Participant is not hosting.": hosting == 0,
            "Participant is repeat host.": hosting > 1,
            "Repeat meetups.": any(count > 1 for count in meetings.values()),
        }
        warnings += sum(warning_weights[name] * flag for name, flag in flags.items())
        severity += (
            weights["Route contains stops with few guests."]
            * 500
            * sum(max(0, 3 - s) for s in sizes)
        )
        severity += (
            weights["Route contains stops with many guests."]
            * 500
            * sum(max(0, s - 3) for s in sizes)
        )
        severity += weights["Participant is repeat host."] * 1000 * max(0, hosting - 1)
        severity += weights["Participant is not hosting."] * 1000 * int(hosting == 0)
        severity += weights["Short Route segment."] * sum(
            ceil(max(0, preferences.minimum_km - d) * 1000) for d in legs
        )
        severity += weights["Long Route segment."] * sum(
            ceil(max(0, d - preferences.maximum_km) * 1000) for d in legs
        )
        # Each repeated pair is counted once, as in the model's pair loop.
        severity += (
            weights["Repeat meetups."]
            * 1000
            * sum(max(0, count - 1) for q, count in meetings.items() if q > p)
        )
        lengths.append(sum(ceil(d * 1000) for d in legs))
        for t, distance in enumerate(legs):
            leg_lengths[t].append(ceil(distance * 1000))
    return warnings, severity, _travel_score(lengths, leg_lengths), sum(lengths)


def _travel_score(lengths, legs):
    """Integer-scaled longest/average distance and mean absolute deviations."""
    n = len(lengths)
    total = sum(lengths)
    leg_totals = [sum(values) for values in legs]
    return (
        4 * n * n * max(lengths)
        + 2 * n * total
        + sum(abs(n * length - total) for length in lengths)
        + sum(
            abs(n * length - leg_total)
            for values, leg_total in zip(legs, leg_totals)
            for length in values
        )
    )


def _stage_deadline(index, now, deadline, maximum_time):
    remaining = max(0, deadline - now)
    allocation = (
        min(0.6 * maximum_time, remaining)
        if index == 0
        else (0.75 * remaining if index in (1, 2) else remaining)
    )
    return min(deadline, now + allocation)


def _valid_hosts(rows, distances, fixed, hard_maximum):
    return (
        all(rows[p][t] == h for (p, t), h in fixed.items())
        and all(rows[h][t] == h for row in rows for t, h in enumerate(row))
        and all(distances[row[t]][row[t + 1]] <= hard_maximum for row in rows for t in range(2))
    )


def _repair_seed(rows, distances, fixed, preferences, rng):
    """Repair a constructive seed while keeping fixed slots and their hosts home."""
    rows = [list(row) for row in rows]
    protected = dict(fixed)
    for (_, t), h in fixed.items():
        if (h, t) in protected and protected[h, t] != h:
            return None
        protected[h, t] = h
    for (p, t), h in protected.items():
        rows[p][t] = h
    n = len(rows)
    maximum = 3 * preferences.maximum_km
    for t in range(3):
        for row in rows:
            h = row[t]
            if (h, t) not in protected:
                rows[h][t] = h
        active = [h for h in range(n) if rows[h][t] == h]
        for p in range(n):
            if rows[rows[p][t]][t] != rows[p][t]:
                rows[p][t] = min(active, key=lambda h: distances[p][h])
    # Small repairs use existing active hosts, so they cannot strand guests.
    for _ in range(3):
        cells = [(p, t) for p in range(n) for t in range(3)]
        rng.shuffle(cells)
        for p, t in cells:
            if (p, t) in protected or rows[p][t] == p:
                continue
            neighbours = [rows[p][s] for s in (t - 1, t + 1) if 0 <= s < 3]
            if all(distances[rows[p][t]][h] <= maximum for h in neighbours):
                continue
            choices = [
                h
                for h in range(n)
                if rows[h][t] == h and all(distances[h][q] <= maximum for q in neighbours)
            ]
            if choices:
                midpoint = (preferences.minimum_km + preferences.maximum_km) / 2
                rows[p][t] = min(
                    choices, key=lambda h: sum(abs(distances[h][q] - midpoint) for q in neighbours)
                )
    return rows if _valid_hosts(rows, distances, fixed, maximum) else None


def _candidate_from_hosts(data, ids, rows, locked_stops, preferences):
    candidate = deepcopy(data)
    candidate.clear_routes()
    for stop in candidate.stops.values():
        stop.guests = []
    existing_stops = {}
    for stop in candidate.stops.values():
        existing_stops.setdefault((stop.host, stop.course), stop)
    stop_ids = {}
    for row in rows:
        for t, h in enumerate(row):
            if (h, t) in stop_ids:
                continue
            existing = candidate.stops.get(locked_stops.get((h, t))) or existing_stops.get(
                (ids[h], COURSES[t])
            )
            if existing is None:
                existing = Stop(
                    id=next_record_id(candidate.stops, "S"), host=ids[h], course=COURSES[t]
                )
                candidate.stops[existing.id] = existing
            stop_ids[h, t] = existing.id
    for pid in ids:
        previous = data.route_for(pid)
        if previous:
            candidate.participants[pid].route_id = previous.id
            candidate.routes[previous.id] = previous.model_copy(deep=True)
    for p, pid in enumerate(ids):
        candidate.assign_route(pid, [stop_ids[h, t] for t, h in enumerate(rows[p])])
    validate_assignment(candidate, preferences)
    return candidate


def _starting_assignment(n, distances, fixed, hard_maximum):
    """A cheap incumbent; fixed slots and required host presence take precedence."""
    rows = [[p] * 3 for p in range(n)]
    for (p, t), h in fixed.items():
        rows[p][t] = h
    for (p, t), h in fixed.items():
        if (h, t) in fixed and fixed[h, t] != h:
            return None
        rows[h][t] = h
    if any(distances[row[t]][row[t + 1]] > hard_maximum for row in rows for t in range(2)):
        return None
    return rows


def _grouped_assignment(n, distances, hard_maximum, preferences=None, rng=None):
    """Nearby blocks of nine use row/column/diagonal groups with no repeated pairs."""
    rows = [[p] * 3 for p in range(n)]
    remaining = set(range(n))
    while len(remaining) >= 3:
        pivot = rng.choice(sorted(remaining)) if rng else min(remaining)
        count = 9 if len(remaining) >= 9 else 3
        if preferences is not None and rng is not None:

            def rank(p, pivot=pivot):
                d = distances[pivot][p]
                deviation = max(0, preferences.minimum_km - d, d - preferences.maximum_km)
                return deviation + 0.1 * d + rng.random() * 0.15

            block = sorted(remaining, key=rank)[:count]
            rng.shuffle(block)
        else:
            block = sorted(remaining, key=lambda p: (distances[pivot][p], p))[:count]
        remaining.difference_update(block)
        trial = {}
        if count == 9:
            row_hosts = [block[i] for i in (0, 4, 8)]
            column_hosts = [block[i] for i in (3, 7, 2)]
            diagonal_hosts = [block[i] for i in (5, 1, 6)]
            for r in range(3):
                for c in range(3):
                    trial[block[3 * r + c]] = [
                        row_hosts[r],
                        column_hosts[c],
                        diagonal_hosts[(r + c) % 3],
                    ]
        else:
            trial = {p: list(block) for p in block}
        if all(
            distances[row[t]][row[t + 1]] <= hard_maximum
            for row in trial.values()
            for t in range(2)
        ):
            for p, row in trial.items():
                rows[p] = row
    return rows


def pre_generate_routes(
    data, preferences, *, maximum_time=30, cancelled=None, progress=None, rng=None
):
    """Random greedy seeds: disjoint hosts, owner hosts appetizer, bounded legs."""
    started = monotonic()
    deadline = started + maximum_time
    cancelled = cancelled if cancelled is not None else Event()
    progress = progress or (lambda message: None)
    rng = rng or Random()
    ids = list(data.participants)
    target = len(ids) // 4
    if not target:
        raise ValueError("Pre-Gen needs at least four participants (25% rounded down).")
    if maximum_time <= 0 or not 0 <= preferences.minimum_km <= preferences.maximum_km:
        raise ValueError("Invalid time limit or segment preferences.")
    if any(p.latitude is None or p.longitude is None for p in data.participants.values()):
        raise ValueError("Find addresses or enter coordinates first.")
    candidate = deepcopy(data)
    used, completed, distances = set(), 0, {}
    owners = [pid for pid in ids if not any(data.route_stops(pid))]
    rng.shuffle(owners)

    def available_stop(host, slot):
        assigned = candidate.route_stops(host)[slot]
        if assigned:
            stop = candidate.stops.get(assigned)
            return assigned if stop and stop.host == host and stop.course == COURSES[slot] else None
        requested = {
            route.stops[slot]
            for route in candidate.routes.values()
            if (stop := candidate.stops.get(route.stops[slot])) is not None
            and stop.host == host
            and stop.course == COURSES[slot]
        }
        if len(requested) > 1:
            return None
        return next(
            iter(requested),
            next(
                (
                    s.id
                    for s in candidate.stops.values()
                    if s.host == host and s.course == COURSES[slot]
                ),
                "",
            ),
        )

    def within_bounds(first, second):
        key = tuple(sorted((first, second)))
        if key not in distances:
            a, b = candidate.participants[first], candidate.participants[second]
            distances[key] = geodesic((a.latitude, a.longitude), (b.latitude, b.longitude)).km
        return preferences.minimum_km <= distances[key] <= preferences.maximum_km

    for owner in owners:
        if completed == target or cancelled.is_set() or monotonic() >= deadline:
            break
        if owner in used:
            continue
        choices = [pid for pid in ids if pid != owner and pid not in used]
        rng.shuffle(choices)
        accepted = False
        for main in choices:
            if accepted or cancelled.is_set() or monotonic() >= deadline:
                break
            if available_stop(main, 1) is None or not within_bounds(owner, main):
                continue
            desserts = [pid for pid in choices if pid != main]
            rng.shuffle(desserts)
            for dessert in desserts:
                if cancelled.is_set() or monotonic() >= deadline:
                    break
                hosts = [owner, main, dessert]
                stops = [available_stop(host, slot) for slot, host in enumerate(hosts)]
                if None in stops or not within_bounds(main, dessert):
                    continue
                trial = deepcopy(candidate)
                for slot, host in enumerate(hosts):
                    if not stops[slot]:
                        stop = Stop(
                            id=next_record_id(trial.stops, "S"), host=host, course=COURSES[slot]
                        )
                        trial.stops[stop.id] = stop
                        stops[slot] = stop.id
                    home = trial.route_stops(host)
                    home[slot] = stops[slot]
                    trial.assign_route(host, home)
                trial.assign_route(owner, stops)
                # Filling a host's slot may create a long adjacent segment on
                # their existing route; reject those triples as well.
                if any(verify_route(trial, pid, preferences)["errors"] for pid in hosts):
                    continue
                candidate = trial
                used.update(hosts)
                completed += 1
                accepted = True
                progress(f"Pre-Gen: {completed}/{target} routes")
                break
    if cancelled.is_set():
        return SolverResult(
            "CANCELLED", "Pre-Gen cancelled; project unchanged.", elapsed=monotonic() - started
        )
    message = f"Pre-Gen created {completed}/{target} disjoint routes."
    if completed < target:
        message += " No more valid triples were found before the time limit or greedy search ended."
    return SolverResult(
        "FEASIBLE" if completed else "INFEASIBLE",
        message,
        candidate if completed else None,
        elapsed=monotonic() - started,
    )


def validate_assignment(data, preferences):
    """Independent check of complete, correctly timed assignments and hard errors."""
    for pid in data.participants:
        route = data.route_for(pid)
        if route is None or not all(route.stops):
            raise ValueError(f"{pid}: incomplete route.")
        for course, sid in zip(COURSES, route.stops, strict=True):
            stop = data.stops.get(sid)
            if stop is None or stop.course != course or stop.host not in data.participants:
                raise ValueError(f"{pid}: invalid {course} stop.")
            attendees = {stop.host, *stop.guests}
            if (
                pid not in attendees
                or len(stop.guests) != len(set(stop.guests))
                or stop.host in stop.guests
            ):
                raise ValueError(f"{pid}: inconsistent attendance.")
        errors = verify_route(data, pid, preferences)["errors"]
        if errors:
            raise ValueError(f"{pid}: {' '.join(errors)}")
    for stop in data.stops.values():
        for pid in stop.guests:
            if (
                pid not in data.participants
                or data.route_stops(pid)[COURSES.index(stop.course)] != stop.id
            ):
                raise ValueError(f"{stop.id}: guest assigned elsewhere.")


def _candidate_pools(n, distances, preferences, fixed, incumbent, width, checkpoint=lambda: None):
    """Course-specific neighborhoods around home, current stops and locked neighbours."""
    maximum = 3 * preferences.maximum_km
    midpoint = (preferences.minimum_km + preferences.maximum_km) / 2
    pools = []
    for p in range(n):
        checkpoint()
        nearest = sorted(range(n), key=lambda h: distances[p][h])
        preferred = sorted(range(n), key=lambda h: abs(distances[p][h] - midpoint))
        base = set(nearest[:width]) | set(preferred[: max(2, width // 2)]) | {p}
        slots = []
        for t in range(3):
            choices = set(range(n)) if width >= n else set(base)
            anchors = [fixed[p, s] for s in (t - 1, t + 1) if (p, s) in fixed]
            if incumbent is not None:
                choices.add(incumbent[p][t])
                anchors += [incumbent[p][s] for s in (t - 1, t + 1) if 0 <= s < 3]
            for anchor in anchors:
                choices.update(
                    sorted(range(n), key=lambda h: abs(distances[anchor][h] - midpoint))[
                        : max(2, width // 3)
                    ]
                )
            if (p, t) in fixed:
                choices = {fixed[p, t]}
            choices = {
                h
                for h in choices
                if fixed.get((h, t), h) == h
                and all(
                    distances[h][fixed[p, s]] <= maximum for s in (t - 1, t + 1) if (p, s) in fixed
                )
            }
            slots.append(choices)
        pools.append(slots)
    # Remove hosts who cannot be home, and choices with no possible adjoining leg.
    changed = True
    while changed:
        changed = False
        for p in range(n):
            checkpoint()
            for t in range(3):
                allowed = {
                    h
                    for h in pools[p][t]
                    if h in pools[h][t]
                    and all(
                        any(distances[h][k] <= maximum for k in pools[p][s])
                        for s in (t - 1, t + 1)
                        if 0 <= s < 3
                    )
                }
                if allowed != pools[p][t]:
                    pools[p][t] = allowed
                    changed = True
    return [[tuple(sorted(slot)) for slot in row] for row in pools]


def _build_model(pools, distances, preferences, fixed, weights, warning_weights, interrupted):
    n = len(pools)
    if any(not slot for row in pools for slot in row):
        return None
    pool_sets = [[set(slot) for slot in row] for row in pools]
    table_cache = {}

    use_short = bool(weights["Short Route segment."])
    use_long = bool(weights["Long Route segment."])

    def transitions(first, second):
        key = (first, second)
        if key not in table_cache:
            table_cache[key] = [
                (
                    h,
                    k,
                    ceil(d * 1000),
                    *((ceil(max(0, preferences.minimum_km - d) * 1000),) if use_short else ()),
                    *((ceil(max(0, d - preferences.maximum_km) * 1000),) if use_long else ()),
                )
                for h in first
                for k in second
                if (d := distances[h][k]) <= 3 * preferences.maximum_km
            ]
        return table_cache[key]

    max_distance = max(
        ceil(d * 1000) for row in distances for d in row if d <= 3 * preferences.maximum_km
    )
    model = cp_model.CpModel()

    def flag(condition, opposite, name):
        result = model.new_bool_var(name)
        model.add(condition).only_enforce_if(result)
        model.add(opposite).only_enforce_if(~result)
        return result

    def any_flag(values, name):
        result = model.new_bool_var(name)
        model.add_max_equality(result, values or [0])
        return result

    def positive(expression, bound, name):
        result = model.new_int_var(0, bound, name)
        model.add_max_equality(result, [expression, 0])
        return result

    x, host, size = {}, {}, {}
    attendees = {(h, t): [] for h in range(n) for t in range(3)}
    for p in range(n):
        if stopped := interrupted():
            return stopped
        for t in range(3):
            host[p, t] = model.new_int_var_from_domain(
                cp_model.Domain.from_values(pools[p][t]), f"host_{p}_{t}"
            )
            choices = []
            for h in pools[p][t]:
                x[p, h, t] = flag(host[p, t] == h, host[p, t] != h, f"attend_{p}_{h}_{t}")
                choices.append(x[p, h, t])
                attendees[h, t].append(x[p, h, t])
            model.add_exactly_one(choices)
            if (p, t) in fixed:
                model.add(host[p, t] == fixed[p, t])
    active_sizes_min, active_sizes_max = [], []
    for h in range(n):
        if stopped := interrupted():
            return stopped
        for t in range(3):
            active = x.get((h, h, t), model.new_constant(0))  # Active hosts attend their own stop.
            for choice in attendees[h, t]:
                model.add(choice <= active)
            size[h, t] = model.new_int_var(0, n, f"size_{h}_{t}")
            model.add(size[h, t] == sum(attendees[h, t]))
            low = model.new_int_var(0, n, f"active_min_{h}_{t}")
            model.add(low == size[h, t]).only_enforce_if(active)
            model.add(low == n).only_enforce_if(~active)
            active_sizes_min.append(low)
            active_sizes_max.append(size[h, t])
    smallest = model.new_int_var(1, n, "smallest_group")
    largest = model.new_int_var(1, n, "largest_group")
    model.add_min_equality(smallest, active_sizes_min)
    model.add_max_equality(largest, active_sizes_max)
    balance = flag(largest - smallest > 1, largest - smallest <= 1, "unbalanced_groups")
    warning_costs = [1000 * balance]
    severity = [
        500000 * positive(largest - smallest - 1, n, "balance_excess"),
        1000 * (largest - smallest),
    ]
    route_lengths = []
    leg_lengths = [[], []]
    repeated_meetings = {p: [] for p in range(n)}
    for p, q in combinations(range(n), 2) if weights["Repeat meetups."] else ():
        if stopped := interrupted():
            return stopped
        possible = [t for t in range(3) if not pool_sets[p][t].isdisjoint(pool_sets[q][t])]
        if len(possible) < 2:
            continue
        meetings = [
            flag(host[p, t] == host[q, t], host[p, t] != host[q, t], f"meet_{p}_{q}_{t}")
            for t in possible
        ]
        if warning_weights["Repeat meetups."]:
            repeated = flag(sum(meetings) > 1, sum(meetings) <= 1, f"repeat_{p}_{q}")
            repeated_meetings[p].append(repeated)
            repeated_meetings[q].append(repeated)
        if weights["Repeat meetups."]:
            severity.append(
                weights["Repeat meetups."]
                * 1000
                * positive(sum(meetings) - 1, 2, f"repeat_count_{p}_{q}")
            )

    for p in range(n):
        if stopped := interrupted():
            return stopped
        per_category = {
            name: []
            for name in (
                "Route contains stops with few guests.",
                "Route contains stops with many guests.",
                "Short Route segment.",
                "Long Route segment.",
                "Participant is not hosting.",
                "Participant is repeat host.",
                "Repeat meetups.",
            )
        }
        hosting = sum(x.get((p, p, t), 0) for t in range(3))
        if weights["Participant is not hosting."]:
            not_hosting = flag(hosting == 0, hosting > 0, f"not_host_{p}")
            per_category["Participant is not hosting."].append(not_hosting)
            severity.append(weights["Participant is not hosting."] * 1000 * not_hosting)
        if warning_weights["Participant is repeat host."]:
            per_category["Participant is repeat host."].append(
                flag(hosting > 1, hosting <= 1, f"repeat_host_{p}")
            )
        if weights["Participant is repeat host."]:
            severity.append(
                weights["Participant is repeat host."]
                * 1000
                * positive(hosting - 1, 2, f"hosting_excess_{p}")
            )
        for t in range(3):
            if not (
                weights["Route contains stops with few guests."]
                or weights["Route contains stops with many guests."]
            ):
                continue
            group = model.new_int_var(1, n, f"group_{p}_{t}")
            choices = pools[p][t]
            index = model.new_int_var(0, len(choices) - 1, f"group_index_{p}_{t}")
            model.add(index == sum(i * x[p, h, t] for i, h in enumerate(choices)))
            model.add_element(index, [size[h, t] for h in choices], group)
            if warning_weights["Route contains stops with few guests."]:
                per_category["Route contains stops with few guests."].append(
                    flag(group < 3, group >= 3, f"few_{p}_{t}")
                )
            if warning_weights["Route contains stops with many guests."]:
                per_category["Route contains stops with many guests."].append(
                    flag(group > 3, group <= 3, f"many_{p}_{t}")
                )
            if weights["Route contains stops with few guests."]:
                severity.append(
                    weights["Route contains stops with few guests."]
                    * 500
                    * positive(3 - group, 3, f"few_excess_{p}_{t}")
                )
            if weights["Route contains stops with many guests."]:
                severity.append(
                    weights["Route contains stops with many guests."]
                    * 500
                    * positive(group - 3, n, f"many_excess_{p}_{t}")
                )
        legs = []
        for t in range(2):
            length = model.new_int_var(0, max_distance, f"distance_{p}_{t}")
            columns = [host[p, t], host[p, t + 1], length]
            if use_short:
                deficit = model.new_int_var(
                    0, ceil(preferences.minimum_km * 1000), f"deficit_{p}_{t}"
                )
                columns.append(deficit)
                if warning_weights["Short Route segment."]:
                    per_category["Short Route segment."].append(
                        flag(deficit > 0, deficit == 0, f"short_{p}_{t}")
                    )
                severity.append(weights["Short Route segment."] * deficit)
            if use_long:
                excess = model.new_int_var(0, max_distance, f"excess_{p}_{t}")
                columns.append(excess)
                if warning_weights["Long Route segment."]:
                    per_category["Long Route segment."].append(
                        flag(excess > 0, excess == 0, f"long_{p}_{t}")
                    )
                severity.append(weights["Long Route segment."] * excess)
            model.add_allowed_assignments(columns, transitions(pools[p][t], pools[p][t + 1]))
            # Positive rounded-up deviation is equivalent to the exact warning
            # comparison; no distance approximation or boundary relaxation.
            legs.append(length)
            leg_lengths[t].append(length)
        total = model.new_int_var(0, 2 * max_distance, f"total_{p}")
        model.add(total == sum(legs))
        route_lengths.append(total)
        per_category["Repeat meetups."] = repeated_meetings[p]
        for category, flags in per_category.items():
            if warning_weights[category]:
                warning_costs.append(
                    warning_weights[category] * any_flag(flags, f"warning_{p}_{category}")
                )
    longest = model.new_int_var(0, 2 * max_distance, "longest_route")
    model.add_max_equality(longest, route_lengths)
    deviations = []
    for section, values in enumerate([route_lengths, *leg_lengths]):
        for p, value in enumerate(values):
            deviation = model.new_int_var(
                0, 2 * n * max_distance, f"travel_deviation_{section}_{p}"
            )
            model.add_abs_equality(deviation, n * value - sum(values))
            deviations.append(deviation)
    travel_balance = 4 * n * n * longest + 2 * n * sum(route_lengths) + sum(deviations)
    objectives = [sum(warning_costs), sum(severity), travel_balance, sum(route_lengths)]
    return model, host, objectives


def solve_routes(
    data,
    preferences,
    ignored_warnings=(),
    *,
    maximum_time=30,
    cancelled=None,
    progress=None,
    respect_existing_routes=False,
    warning_multipliers=None,
    minimize_warning_counts=None,
    search_workers=None,
):
    """Return an isolated candidate; never mutate the input, even on failure/cancel."""
    started = monotonic()
    deadline = started + maximum_time
    cancelled = cancelled if cancelled is not None else Event()
    progress = progress or (lambda message: None)
    ids = list(data.participants)
    n = len(ids)
    id_to_index = {pid: p for p, pid in enumerate(ids)}
    if not n:
        raise ValueError("Add participants before generating routes.")
    if (
        maximum_time <= 0
        or preferences.minimum_km < 0
        or preferences.maximum_km < preferences.minimum_km
    ):
        raise ValueError("Invalid time limit or segment preferences.")
    missing = [
        pid
        for pid in ids
        if data.participants[pid].latitude is None or data.participants[pid].longitude is None
    ]
    if missing:
        raise ValueError("Find addresses or enter coordinates first: " + ", ".join(missing))
    settings = ProjectSettings(
        warning_multipliers=warning_multipliers or {},
        minimize_warning_counts=minimize_warning_counts or {},
    )
    multipliers = settings.warning_multipliers
    weights = {
        category: 0 if category in ignored_warnings else round(multiplier * 1000)
        for category, multiplier in multipliers.items()
    }
    warning_weights = {
        category: weight if settings.minimize_warning_counts[category] else 0
        for category, weight in weights.items()
    }
    locked_stops, fixed = {}, {}
    if respect_existing_routes:
        for pid in ids:
            route = data.route_for(pid)
            if route is None:
                continue
            for t, sid in enumerate(route.stops):
                if not sid:
                    continue
                stop = data.stops.get(sid)
                if stop is None or stop.host not in data.participants or stop.course != COURSES[t]:
                    raise ValueError(
                        f"{pid}: existing route contains an invalid {COURSES[t]} stop."
                    )
                key = (id_to_index[stop.host], t)
                fixed[id_to_index[pid], t] = key[0]
                if key in locked_stops and locked_stops[key] != sid:
                    raise ValueError(
                        f"{pid}: existing routes require different stops at the same host during {COURSES[t]}."
                    )
                locked_stops[key] = sid
            # Empty slots can be completed; conflicts in assigned slots cannot.
            errors = [
                error
                for error in verify_route(data, pid, preferences)["errors"]
                if error != "Empty route."
            ]
            if errors:
                raise ValueError(f"{pid}: existing route cannot be kept: {' '.join(errors)}")

    # Visiting a locked stop also fixes its host at home for that course.
    for (_, t), h in list(fixed.items()):
        if (h, t) in fixed and fixed[h, t] != h:
            raise ValueError(
                f"{ids[h]}: existing route cannot be kept: Host already assigned to other stop."
            )
        fixed[h, t] = h

    best_hosts, best_scores = None, ()

    def interrupted():
        if cancelled.is_set():
            return SolverResult(
                "CANCELLED",
                "Generation cancelled; the project was kept.",
                elapsed=monotonic() - started,
            )
        if monotonic() >= deadline:
            if best_hosts is not None:
                candidate = _candidate_from_hosts(data, ids, best_hosts, locked_stops, preferences)
                return SolverResult(
                    "FEASIBLE",
                    "Valid starting assignment retained; time limit reached during preparation.",
                    candidate,
                    best_scores,
                    monotonic() - started,
                )
            return SolverResult(
                "UNKNOWN",
                "Time limit reached before a valid assignment was found.",
                elapsed=monotonic() - started,
            )
        return None

    progress("Preparing distances and assignment constraints…")
    distances = [[0.0] * n for _ in ids]
    coordinates = [
        (data.participants[pid].latitude, data.participants[pid].longitude) for pid in ids
    ]
    metric, distance_cache = geodesic(), {}
    for p in range(n):
        if stopped := interrupted():
            return stopped
        for q in range(p + 1, n):
            key = tuple(sorted((coordinates[p], coordinates[q])))
            if key not in distance_cache:
                distance_cache[key] = 0.0 if key[0] == key[1] else metric.measure(*key)
            distances[p][q] = distances[q][p] = distance_cache[key]
    seed = _starting_assignment(n, distances, fixed, 3 * preferences.maximum_km)
    if seed is not None:
        best_hosts, best_scores = (
            seed,
            _assignment_scores(seed, distances, preferences, weights, warning_weights),
        )
    rng = Random(0)
    seed_deadline = min(deadline, monotonic() + min(1.0, maximum_time * 0.05))

    def consider(rows):
        nonlocal best_hosts, best_scores
        if rows is not None:
            scores = _assignment_scores(rows, distances, preferences, weights, warning_weights)
            if best_hosts is None or scores < best_scores:
                best_hosts, best_scores = rows, scores

    current = []
    for pid in ids:
        stops = [data.stops.get(sid) for sid in data.route_stops(pid)]
        if any(
            stop is None or stop.host not in id_to_index or stop.course != COURSES[t]
            for t, stop in enumerate(stops)
        ):
            break
        current.append([id_to_index[stop.host] for stop in stops])
    if len(current) == n and _valid_hosts(current, distances, fixed, 3 * preferences.maximum_km):
        consider(current)
    for attempt in range(8):
        if cancelled.is_set() or monotonic() >= seed_deadline:
            break
        grouped = _grouped_assignment(
            n,
            distances,
            3 * preferences.maximum_km,
            preferences if attempt else None,
            rng if attempt else None,
        )
        consider(_repair_seed(grouped, distances, fixed, preferences, rng))
    # Guest swaps preserve host presence and group sizes while improving travel/social variety.
    for _ in range(100):
        if best_hosts is None or n < 2 or cancelled.is_set() or monotonic() >= seed_deadline:
            break
        p, q = rng.sample(range(n), 2)
        t = rng.randrange(3)
        if (p, t) in fixed or (q, t) in fixed or best_hosts[p][t] == p or best_hosts[q][t] == q:
            continue
        trial = [list(row) for row in best_hosts]
        trial[p][t], trial[q][t] = trial[q][t], trial[p][t]
        if _valid_hosts(trial, distances, fixed, 3 * preferences.maximum_km):
            consider(trial)
    if best_hosts is not None:
        progress("Feasible starting assignment ready; building optimization model…")
    restricted = n > 36
    width = 12 if restricted else n
    model = host = objectives = pools = None
    labels = [
        "Minimizing warnings",
        "Reducing violation severity",
        "Balancing travel",
        "Reducing total travel",
    ]
    caps = []
    proven = []
    workers = (
        search_workers if search_workers is not None else min(4, max(1, (cpu_count() or 2) - 1))
    )
    if not isinstance(workers, int) or workers < 1:
        raise ValueError("Search workers must be a positive integer.")

    def retain(rows, scores):
        nonlocal best_hosts, best_scores
        if best_hosts is None or scores < best_scores:
            best_hosts, best_scores = rows, scores

    def improve_locally(limit):
        """Use short leftover slices without paying CP-SAT's model-loading cost again."""
        for _ in range(2000):
            if best_hosts is None or n < 2 or cancelled.is_set() or monotonic() >= limit:
                break
            p, q = rng.sample(range(n), 2)
            t = rng.randrange(3)
            if (p, t) in fixed:
                continue
            trial = [list(row) for row in best_hosts]
            if rng.random() < 0.5:
                if (q, t) in fixed or trial[p][t] == p or trial[q][t] == q:
                    continue
                trial[p][t], trial[q][t] = trial[q][t], trial[p][t]
            else:
                # A host may leave only if no guests would be stranded.
                if trial[p][t] == p and any(row[t] == p for i, row in enumerate(trial) if i != p):
                    continue
                trial[p][t] = q if trial[q][t] == q else p
            if not _valid_hosts(trial, distances, fixed, 3 * preferences.maximum_km):
                continue
            scores = _assignment_scores(trial, distances, preferences, weights, warning_weights)
            if all(cap is None or scores[i] <= cap for i, cap in enumerate(caps)):
                retain(trial, scores)

    class Incumbent(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            scores = tuple(self.value(item) for item in objectives)
            if best_hosts is None or scores < best_scores:
                retain([[self.value(host[p, t]) for t in range(3)] for p in range(n)], scores)

    for stage, label in enumerate(labels):
        if cancelled.is_set() or monotonic() >= deadline:
            break
        stage_end = _stage_deadline(stage, monotonic(), deadline, maximum_time)
        stage_proven = False
        progress(label + "\u2026")
        improve_locally(min(stage_end, monotonic() + min(0.25, (stage_end - monotonic()) * 0.1)))
        # Both warning and severity terms are nonnegative. Zero is a global
        # lower bound, so no search is needed to prove these priorities optimal.
        if stage < 2 and best_hosts is not None and best_scores[stage] == 0:
            proven.append(True)
            caps.append(0)
            if model is not None:
                model.add(objectives[stage] == 0)
            continue
        if (
            model is not None
            and best_hosts is not None
            and any(best_hosts[p][t] not in pools[p][t] for p in range(n) for t in range(3))
        ):
            model = None

        def build_checkpoint(limit=stage_end):
            if cancelled.is_set() or monotonic() >= limit:
                raise TimeoutError

        def build_interrupted():
            build_checkpoint()

        while monotonic() < stage_end and not cancelled.is_set():
            if model is None:
                try:
                    pools = _candidate_pools(
                        n, distances, preferences, fixed, best_hosts, width, build_checkpoint
                    )
                    built = _build_model(
                        pools,
                        distances,
                        preferences,
                        fixed,
                        weights,
                        warning_weights,
                        build_interrupted,
                    )
                except TimeoutError:
                    break
                if built is None:
                    if width < n:
                        width = min(n, width * 2)
                        continue
                    if best_hosts is None:
                        return SolverResult(
                            "INFEASIBLE",
                            "No assignment satisfies all hard constraints.",
                            elapsed=monotonic() - started,
                        )
                    break
                model, host, objectives = built
                for index, cap in enumerate(caps):
                    if cap is not None:
                        model.add(objectives[index] <= cap)
                if best_hosts is not None:
                    model.add(objectives[0] <= best_scores[0])
            if monotonic() >= stage_end:
                break
            table_cells = sum(len(c.table.values) for c in model.proto.constraints if c.has_table())
            # Import/presolve cannot always stop instantly. Tiny remaining slices
            # are better spent making validated local improvements to the incumbent.
            minimum_search_time = max(0.03, table_cells / 250_000)
            if best_hosts is not None and stage_end - monotonic() < minimum_search_time:
                break
            model.clear_hints()
            if best_hosts is not None:
                for p in range(n):
                    for t in range(3):
                        model.add_hint(host[p, t], best_hosts[p][t])
            model.minimize(objectives[stage])
            solver = cp_model.CpSolver()
            remaining = stage_end - monotonic()
            # Give restricted searches one opportunity to expand before the stage ends.
            can_expand = width < min(n, 48) and remaining > max(2.0, 4 * minimum_search_time)
            slice_end = min(
                stage_end, monotonic() + (remaining * 0.55 if can_expand else remaining)
            )
            loading_allowance = table_cells / 750_000 if table_cells > 50_000 else 0
            solver.parameters.max_time_in_seconds = max(
                0.001, slice_end - monotonic() - loading_allowance
            )
            solver.parameters.num_search_workers = workers
            solver.parameters.random_seed = 0
            done = Event()

            def monitor(done=done, solver=solver, limit=slice_end):
                while not done.wait(0.02):
                    if cancelled.is_set() or monotonic() >= limit:
                        solver.stop_search()

            watcher = Thread(target=monitor, daemon=True)
            watcher.start()
            try:
                status = solver.solve(model, Incumbent())
            finally:
                done.set()
                watcher.join()
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                scores = tuple(solver.value(item) for item in objectives)
                retain([[solver.value(host[p, t]) for t in range(3)] for p in range(n)], scores)
                stage_proven = (
                    status == cp_model.OPTIMAL
                    and width >= n
                    and best_scores[stage] == scores[stage]
                )
            elif status == cp_model.MODEL_INVALID:
                raise ValueError("Invalid assignment model: " + model.validate())
            elif status == cp_model.INFEASIBLE and best_hosts is None and width >= n:
                return SolverResult(
                    "INFEASIBLE",
                    "No assignment satisfies all hard constraints.",
                    elapsed=monotonic() - started,
                )
            if can_expand and monotonic() + 0.1 < stage_end:
                width = min(n, 48, width * 2)
                model = None
                continue
            break
        if not stage_proven:
            improve_locally(stage_end)
        if (
            model is not None
            and best_hosts is not None
            and any(best_hosts[p][t] not in pools[p][t] for p in range(n) for t in range(3))
        ):
            model = None
        proven.append(stage_proven)
        if best_hosts is None:
            # Still search for feasibility in the next reserved time slice.
            caps.append(None)
        else:
            caps.append(best_scores[stage])
            if model is not None:
                model.add(objectives[stage] <= best_scores[stage])
    if cancelled.is_set():
        return SolverResult(
            "CANCELLED",
            "Generation cancelled; the project was kept.",
            elapsed=monotonic() - started,
        )
    if best_hosts is None:
        return SolverResult(
            "UNKNOWN",
            "No assignment found in the candidate neighbourhoods; full infeasibility was not proven."
            if restricted
            else "Time limit reached without a valid assignment. Try a longer maximum time.",
            elapsed=monotonic() - started,
        )
    candidate = _candidate_from_hosts(data, ids, best_hosts, locked_stops, preferences)
    if respect_existing_routes:
        for pid in ids:
            previous = data.route_for(pid)
            if previous:
                generated = candidate.route_for(pid)
                if generated.id != previous.id or any(
                    old and old != new
                    for old, new in zip(previous.stops, generated.stops, strict=True)
                ):
                    raise ValueError(f"{pid}: generated assignment changed a locked route.")
    status = "OPTIMAL" if len(proven) == len(labels) and all(proven) else "FEASIBLE"
    message = (
        "Optimal assignment found."
        if status == "OPTIMAL"
        else "Valid assignment found using candidate neighbourhoods; global optimality was not proven."
        if restricted
        else "Valid assignment found; optimality was not proven within the time limit."
    )
    return SolverResult(status, message, candidate, best_scores, monotonic() - started)


class SolverWorker(QThread):
    progress = Signal(str)

    def __init__(
        self,
        data,
        preferences,
        ignored_warnings,
        maximum_time,
        parent=None,
        *,
        respect_existing_routes=False,
        warning_multipliers=None,
        minimize_warning_counts=None,
        pre_generate=False,
    ):
        super().__init__(parent)
        self.data = deepcopy(data)
        self.preferences = deepcopy(preferences)
        self.ignored_warnings = set(ignored_warnings)
        self.maximum_time = maximum_time
        self.respect_existing_routes = respect_existing_routes
        self.warning_multipliers = dict(warning_multipliers or {})
        self.minimize_warning_counts = dict(minimize_warning_counts or {})
        self.pre_generate = pre_generate
        self.cancelled = Event()
        self.result = None

    def cancel(self):
        self.cancelled.set()

    def run(self):
        try:
            if self.pre_generate:
                self.result = pre_generate_routes(
                    self.data,
                    self.preferences,
                    maximum_time=self.maximum_time,
                    cancelled=self.cancelled,
                    progress=self.progress.emit,
                )
                return
            self.result = solve_routes(
                self.data,
                self.preferences,
                self.ignored_warnings,
                maximum_time=self.maximum_time,
                cancelled=self.cancelled,
                progress=self.progress.emit,
                respect_existing_routes=self.respect_existing_routes,
                warning_multipliers=self.warning_multipliers,
                minimize_warning_counts=self.minimize_warning_counts,
            )
        except (ValueError, TypeError, RuntimeError, OverflowError, KeyError) as error:
            self.result = SolverResult("FAILED", str(error))
